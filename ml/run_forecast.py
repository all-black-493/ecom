"""Standalone Prophet demand-forecasting job.

Runs locally without Airflow. Reads training data from Postgres
(falls back to a sample CSV if Postgres is unreachable), trains one
top-line model + one per category, writes:

  * `app/static/forecast.json` — top-line series for the in-app dashboard
  * `ml/forecast_categories.csv` — per-category for Looker Studio import
  * `ml/forecast_metrics.json` — walk-forward MAPE / coverage

Usage:
    python ml/run_forecast.py --horizon 30 --history-days 540
"""

from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path

import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("forecast")

ROOT = Path(__file__).resolve().parents[1]
APP_STATIC = ROOT / "app" / "static"


def load_history(history_days: int) -> pd.DataFrame:
    """Returns DataFrame with columns: date, category_name, revenue."""
    db_url = os.environ.get("DATABASE_URL")
    if db_url:
        try:
            from sqlalchemy import create_engine

            engine = create_engine(db_url)
            sql = f"""
                SELECT date_trunc('day', o.placed_at)::date AS date,
                       c.name AS category_name,
                       SUM(oi.quantity * oi.unit_price)::float AS revenue
                FROM orders o
                JOIN order_items oi ON oi.order_id = o.id
                JOIN products p ON p.id = oi.product_id
                JOIN categories c ON c.id = p.category_id
                WHERE o.status NOT IN ('cancelled','refunded')
                  AND o.placed_at >= NOW() - INTERVAL '{history_days} days'
                GROUP BY 1, 2
                ORDER BY 1
            """
            df = pd.read_sql(sql, engine)
            log.info("loaded %d daily rows from Postgres", len(df))
            return df
        except Exception as e:  # noqa: BLE001
            log.warning("postgres load failed (%s); falling back to sample", e)

    sample = ROOT / "ml" / "sample_history.csv"
    if sample.exists():
        return pd.read_csv(sample, parse_dates=["date"])
    raise SystemExit("No data source available — start Postgres or provide ml/sample_history.csv")


def fit_one(df: pd.DataFrame, horizon: int) -> pd.DataFrame:
    """Fit Prophet on a single series. df: ds, y."""
    from prophet import Prophet  # imported inside the call to keep import-time cheap

    m = Prophet(
        weekly_seasonality=True,
        yearly_seasonality=len(df) >= 365,
        daily_seasonality=False,
        interval_width=0.80,
    )
    m.fit(df)
    future = m.make_future_dataframe(periods=horizon)
    pred = m.predict(future).tail(horizon)
    return pred[["ds", "yhat", "yhat_lower", "yhat_upper"]]


def walk_forward_mape(df: pd.DataFrame, n_splits: int = 3, horizon: int = 30) -> dict:
    """Quick back-test: last n_splits months."""
    from prophet import Prophet

    df = df.sort_values("ds").reset_index(drop=True)
    if len(df) < horizon * (n_splits + 1):
        return {"mape": None, "coverage": None, "note": "insufficient history"}

    mapes, coverages = [], []
    for k in range(n_splits, 0, -1):
        cut = len(df) - k * horizon
        train, test = df.iloc[:cut], df.iloc[cut : cut + horizon]
        m = Prophet(weekly_seasonality=True, yearly_seasonality=True, interval_width=0.80)
        m.fit(train)
        fcst = m.predict(test[["ds"]])
        merged = test.merge(fcst[["ds", "yhat", "yhat_lower", "yhat_upper"]], on="ds")
        mape = (abs(merged["y"] - merged["yhat"]) / merged["y"].replace(0, pd.NA)).mean()
        cov = ((merged["y"] >= merged["yhat_lower"]) & (merged["y"] <= merged["yhat_upper"])).mean()
        mapes.append(float(mape))
        coverages.append(float(cov))
    return {
        "mape_top_line_mean": sum(mapes) / len(mapes),
        "mape_top_line_per_split": mapes,
        "coverage_80_mean": sum(coverages) / len(coverages),
        "n_splits": n_splits,
        "horizon_days": horizon,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--horizon", type=int, default=30)
    parser.add_argument("--history-days", type=int, default=540)
    args = parser.parse_args()

    history = load_history(args.history_days)
    log.info("history range: %s → %s", history["date"].min(), history["date"].max())

    # Top-line
    top_df = history.groupby("date", as_index=False)["revenue"].sum().rename(
        columns={"date": "ds", "revenue": "y"}
    )
    top_df["ds"] = pd.to_datetime(top_df["ds"])

    log.info("fitting top-line model on %d days…", len(top_df))
    top_fcst = fit_one(top_df, args.horizon)
    top_fcst["ds"] = top_fcst["ds"].dt.strftime("%Y-%m-%d")
    APP_STATIC.mkdir(parents=True, exist_ok=True)
    out_path = APP_STATIC / "forecast.json"
    top_fcst.to_json(out_path, orient="records")
    log.info("wrote %s", out_path)

    # Optional: upload to GCS so the always-on Cloud Run app can read the
    # latest forecast. Set FORECAST_GCS_URI=gs://bucket/path/forecast.json
    # to enable. Without this, the file is ephemeral on Cloud Run Jobs.
    gcs_uri = os.environ.get("FORECAST_GCS_URI", "").strip()
    if gcs_uri.startswith("gs://"):
        try:
            from google.cloud import storage  # type: ignore

            bucket_name, _, blob_path = gcs_uri[len("gs://") :].partition("/")
            client = storage.Client()
            blob = client.bucket(bucket_name).blob(blob_path or "forecast.json")
            blob.cache_control = "public, max-age=300"
            blob.upload_from_filename(out_path, content_type="application/json")
            log.info("uploaded to %s", gcs_uri)
        except Exception as e:  # noqa: BLE001
            log.warning("GCS upload failed (%s); local file remains", e)

    # Per category
    cats = history["category_name"].unique()
    log.info("fitting %d category models…", len(cats))
    per_cat = []
    for cat in cats:
        cdf = (
            history[history["category_name"] == cat]
            .groupby("date", as_index=False)["revenue"]
            .sum()
            .rename(columns={"date": "ds", "revenue": "y"})
        )
        cdf["ds"] = pd.to_datetime(cdf["ds"])
        if len(cdf) < 60:
            continue
        f = fit_one(cdf, args.horizon)
        f["category_name"] = cat
        per_cat.append(f)
    cat_out = pd.concat(per_cat, ignore_index=True)
    cat_out_path = ROOT / "ml" / "forecast_categories.csv"
    cat_out.to_csv(cat_out_path, index=False)
    log.info("wrote %s", cat_out_path)

    # Optional: write to BigQuery so Looker/Data Studio can blend the
    # forecast with mart_daily_revenue. Set FORECAST_BQ_TABLE=project.dataset.table
    # to enable. Appends with the current model_run_at; older runs stay in the
    # table as historical reference / back-testing record.
    # IMPORTANT: this block MUST run after both top_fcst and per_cat are fully
    # populated. If you move it earlier, Python's scoping rules will treat
    # per_cat as a local variable assigned later → UnboundLocalError at runtime.
    bq_table = os.environ.get("FORECAST_BQ_TABLE", "").strip()
    if bq_table:
        try:
            import pandas_gbq  # lazy: only needed if FORECAST_BQ_TABLE is set

            run_ts = pd.Timestamp.utcnow()
            top_line = pd.DataFrame(
                [
                    {
                        "forecast_date": pd.to_datetime(r["ds"]).date(),
                        "category_name": "__total__",
                        "yhat": float(r["yhat"]),
                        "yhat_lower": float(r["yhat_lower"]),
                        "yhat_upper": float(r["yhat_upper"]),
                        "model_run_at": run_ts,
                    }
                    for r in top_fcst.to_dict(orient="records")
                ]
            )

            per_cat_rows: list[dict] = []
            for cat_df in per_cat:
                cat = cat_df["category_name"].iloc[0]
                for r in cat_df.to_dict(orient="records"):
                    per_cat_rows.append(
                        {
                            "forecast_date": pd.to_datetime(r["ds"]).date(),
                            "category_name": cat,
                            "yhat": float(r["yhat"]),
                            "yhat_lower": float(r["yhat_lower"]),
                            "yhat_upper": float(r["yhat_upper"]),
                            "model_run_at": run_ts,
                        }
                    )

            out_df = pd.concat([top_line, pd.DataFrame(per_cat_rows)], ignore_index=True)
            project_id, dataset, table = bq_table.split(".")
            pandas_gbq.to_gbq(
                out_df,
                destination_table=f"{dataset}.{table}",
                project_id=project_id,
                if_exists="append",
                progress_bar=False,
            )
            log.info("wrote %d rows to %s", len(out_df), bq_table)
        except Exception as e:  # noqa: BLE001
            log.warning("BigQuery write failed (%s); JSON outputs still produced", e)

    # Evaluation
    log.info("running walk-forward back-test…")
    metrics = walk_forward_mape(top_df, n_splits=3, horizon=args.horizon)
    (ROOT / "ml" / "forecast_metrics.json").write_text(json.dumps(metrics, indent=2))
    log.info("metrics: %s", metrics)


if __name__ == "__main__":
    main()
