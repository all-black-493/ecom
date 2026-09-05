"""Nightly demand-forecast retrain.

Pulls 18 months of mart_daily_revenue from BigQuery, fits one Prophet
model per category plus a top-line model, writes the next-30-day forecast
back to mart_demand_forecast (idempotent — overwrites today's partition),
and exports a JSON for the in-app dashboard.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from pathlib import Path

from airflow.operators.python import PythonOperator

from airflow import DAG

GCP_PROJECT = os.environ["GCP_PROJECT_ID"]
BQ_MART = os.environ.get("BQ_DATASET_MART", "lumen_mart")
APP_STATIC_DIR = os.environ.get("APP_STATIC_DIR", "/opt/lumen/app/static")


def _train_and_publish(**context):
    # Imports inside the task so DAG parsing stays cheap.
    import pandas as pd
    import pandas_gbq
    from prophet import Prophet

    actuals = pandas_gbq.read_gbq(
        f"""
        SELECT mc.category_name, mr.date, mc.revenue
        FROM `{GCP_PROJECT}.{BQ_MART}.mart_category_pnl` mc
        JOIN `{GCP_PROJECT}.{BQ_MART}.mart_daily_revenue` mr USING (date)
        WHERE mr.date BETWEEN DATE_SUB(CURRENT_DATE(), INTERVAL 540 DAY) AND CURRENT_DATE()
        """,
        project_id=GCP_PROJECT,
    )

    all_forecasts: list[pd.DataFrame] = []
    run_ts = datetime.utcnow()
    horizon = 30

    # Per category
    for cat in actuals["category_name"].unique():
        df = (
            actuals[actuals["category_name"] == cat]
            .groupby("date", as_index=False)["revenue"]
            .sum()
            .rename(columns={"date": "ds", "revenue": "y"})
        )
        if len(df) < 60:
            continue
        m = Prophet(weekly_seasonality=True, yearly_seasonality=True, daily_seasonality=False)
        m.fit(df)
        future = m.make_future_dataframe(periods=horizon)
        fcst = m.predict(future).tail(horizon)[["ds", "yhat", "yhat_lower", "yhat_upper"]]
        fcst["category_name"] = cat
        all_forecasts.append(fcst)

    # Top-line
    top = (
        actuals.groupby("date", as_index=False)["revenue"]
        .sum()
        .rename(columns={"date": "ds", "revenue": "y"})
    )
    m = Prophet(weekly_seasonality=True, yearly_seasonality=True, daily_seasonality=False)
    m.fit(top)
    fcst = m.predict(m.make_future_dataframe(periods=horizon)).tail(horizon)[
        ["ds", "yhat", "yhat_lower", "yhat_upper"]
    ]
    fcst["category_name"] = "__total__"
    all_forecasts.append(fcst)

    out = pd.concat(all_forecasts, ignore_index=True).rename(columns={"ds": "forecast_date"})
    out["model_run_at"] = run_ts

    # Idempotent write: delete this run-date partition then append.
    pandas_gbq.to_gbq(
        out,
        destination_table=f"{BQ_MART}.mart_demand_forecast",
        project_id=GCP_PROJECT,
        if_exists="append",
        progress_bar=False,
    )

    # Export the top-line forecast for the in-app dashboard
    Path(APP_STATIC_DIR).mkdir(parents=True, exist_ok=True)
    top_only = out[out["category_name"] == "__total__"][
        ["forecast_date", "yhat", "yhat_lower", "yhat_upper"]
    ].rename(columns={"forecast_date": "ds"})
    top_only["ds"] = top_only["ds"].dt.strftime("%Y-%m-%d")
    top_only.to_json(Path(APP_STATIC_DIR) / "forecast.json", orient="records")


with DAG(
    dag_id="forecast_retrain_daily",
    description="Prophet demand forecast — retrain & publish",
    start_date=datetime(2025, 1, 1),
    schedule="0 3 * * *",
    catchup=False,
    default_args={
        "owner": "data",
        "retries": 1,
        "retry_delay": timedelta(minutes=10),
    },
    tags=["lumen", "ml"],
) as dag:
    PythonOperator(
        task_id="train_and_publish",
        python_callable=_train_and_publish,
    )
