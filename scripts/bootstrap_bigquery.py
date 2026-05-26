"""One-shot bulk load Cloud SQL Postgres → BigQuery lumen_raw.

Use this when you don't want to run Airflow/Composer yet — populates the
warehouse from your seeded Postgres so Looker/Data Studio reports start
showing real data. The Airflow DAG in airflow/dags/ replaces this in
production by streaming incremental updates hourly.

Run via:
    cloud-sql-proxy "$PROJECT_ID:$REGION:lumen-pg" &
    PROXY_PID=$!
    sleep 3
    DATABASE_URL="postgresql+psycopg2://lumen:PASSWORD@127.0.0.1:5432/lumen" \\
      GCP_PROJECT_ID=$PROJECT_ID BQ_DATASET_RAW=lumen_raw \\
      .venv/bin/python scripts/bootstrap_bigquery.py
    kill $PROXY_PID

Each Postgres table is dumped into a pandas DataFrame and pushed to the
matching BigQuery table with WRITE_TRUNCATE. Total runtime for the seed
data (~80k rows across 13 tables) is around 2-3 minutes.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

import pandas as pd
from sqlalchemy import create_engine, text

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s")
log = logging.getLogger("bootstrap-bq")

# Tables to copy from Postgres → BigQuery. Order doesn't matter (no FKs in BQ).
TABLES = [
    "categories",
    "customers",
    "products",
    "product_variants",
    "orders",
    "order_items",
    "carts",
    "cart_items",
    "inventory_levels",
    "stock_movements",
    "product_events",
    "promotions",
    "promotion_redemptions",
    "page_views",
    "addresses",
    "payments",
    "shipments",
]


def copy_table(engine, project_id: str, dataset: str, table: str) -> int:
    """Read one Postgres table and write it to BigQuery. Returns row count."""
    import pandas_gbq

    df = pd.read_sql(text(f"SELECT * FROM {table}"), engine)
    if df.empty:
        log.info("  %s — empty, skipping", table)
        return 0

    # BigQuery doesn't like enum types; cast to string.
    for col in df.columns:
        if df[col].dtype.name == "object":
            sample = df[col].dropna().head(1)
            if not sample.empty and not isinstance(sample.iloc[0], (str, bytes, dict)):
                df[col] = df[col].astype(str)

    # Add the _ingested_at column that lumen_raw tables expect.
    df["_ingested_at"] = datetime.now(timezone.utc)

    pandas_gbq.to_gbq(
        df,
        destination_table=f"{dataset}.{table}",
        project_id=project_id,
        if_exists="replace",
        progress_bar=False,
    )
    log.info("  %s → %s.%s  (%d rows)", table, dataset, table, len(df))
    return len(df)


def main() -> None:
    db_url = os.environ.get("DATABASE_URL")
    project_id = os.environ.get("GCP_PROJECT_ID")
    dataset = os.environ.get("BQ_DATASET_RAW", "lumen_raw")

    if not db_url or not project_id:
        raise SystemExit("set DATABASE_URL and GCP_PROJECT_ID before running")

    engine = create_engine(db_url)
    log.info("bulk loading %d tables → %s.%s.*", len(TABLES), project_id, dataset)

    total = 0
    for t in TABLES:
        try:
            total += copy_table(engine, project_id, dataset, t)
        except Exception as e:  # noqa: BLE001
            log.error("  %s — FAILED: %s", t, e)

    log.info("done. %d rows copied total.", total)
    log.info("now refresh your Data Studio report — the marts should populate.")


if __name__ == "__main__":
    main()
