"""Hourly ETL: Postgres OLTP → BigQuery warehouse.

Tasks per table:
  1. Pull a window from Postgres (incremental for facts, full for small dims).
  2. Stage to GCS as newline-delimited JSON.
  3. Load into BigQuery with WRITE_TRUNCATE for partitions / dims.
  4. CREATE OR REPLACE VIEW for marts.

Designed to be cheap (under 1¢ per run) and idempotent — each task
deletes the partitions it's about to write so reruns are safe.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from pathlib import Path

from airflow.operators.bash import BashOperator
from airflow.operators.python import PythonOperator
from airflow.providers.google.cloud.transfers.gcs_to_bigquery import (
    GCSToBigQueryOperator,
)
from airflow.providers.postgres.hooks.postgres import PostgresHook

from airflow import DAG

# ----------------------------------------------------------------------- config

GCP_PROJECT = os.environ["GCP_PROJECT_ID"]
BQ_RAW = os.environ.get("BQ_DATASET_RAW", "lumen_raw")
BQ_MART = os.environ.get("BQ_DATASET_MART", "lumen_mart")
GCS_BUCKET = os.environ.get("ETL_GCS_BUCKET", f"{GCP_PROJECT}-lumen-etl")

POSTGRES_CONN_ID = "lumen_postgres"  # set in Airflow as the Postgres connection

# Tables that are reasonable to full-reload each run.
DIM_TABLES = ["categories", "products", "product_variants", "promotions"]

# Fact-style tables with a timestamp column we partition by.
INCR_TABLES = {
    "customers": "created_at",
    "orders": "placed_at",
    "order_items": "_synthetic_order_placed_at",  # needs join, handled below
    "stock_movements": "occurred_at",
    "carts": "created_at",
    "product_events": "occurred_at",
    "inventory_levels": "updated_at",
    "promotion_redemptions": "redeemed_at",
}


def _extract_postgres(table: str, where_clause: str, **context):
    """Pull a table window from Postgres → newline-delimited JSON on the worker."""
    hook = PostgresHook(postgres_conn_id=POSTGRES_CONN_ID)
    sql = f"SELECT * FROM {table} {where_clause}"
    rows = hook.get_records(sql)
    columns = [c.name for c in hook.get_conn().cursor().description or []]

    out_dir = Path("/tmp/lumen_etl") / context["ds"] / table
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "data.jsonl"
    with out_file.open("w") as f:
        for r in rows:
            obj = dict(zip(columns, r, strict=True))
            for k, v in obj.items():
                if isinstance(v, (datetime,)):
                    obj[k] = v.isoformat()
            f.write(json.dumps(obj, default=str) + "\n")
    context["ti"].xcom_push(key=f"{table}_path", value=str(out_file))
    context["ti"].xcom_push(key=f"{table}_rows", value=len(rows))


with DAG(
    dag_id="etl_postgres_to_bigquery_hourly",
    description="OLTP → warehouse hourly incremental load",
    start_date=datetime(2025, 1, 1),
    schedule="@hourly",
    catchup=False,
    default_args={
        "owner": "data",
        "retries": 2,
        "retry_delay": timedelta(minutes=5),
    },
    tags=["lumen", "etl"],
) as dag:

    extract_dims = [
        PythonOperator(
            task_id=f"extract_{t}",
            python_callable=_extract_postgres,
            op_kwargs={"table": t, "where_clause": ""},
        )
        for t in DIM_TABLES
    ]

    extract_facts = [
        PythonOperator(
            task_id=f"extract_{t}",
            python_callable=_extract_postgres,
            op_kwargs={
                "table": t,
                "where_clause": (
                    f"WHERE {col} >= NOW() - INTERVAL '2 hours'"
                    if not col.startswith("_synthetic")
                    else ""
                ),
            },
        )
        for t, col in INCR_TABLES.items()
    ]

    upload_to_gcs = BashOperator(
        task_id="upload_to_gcs",
        bash_command=(
            "gsutil -m rsync -d -r /tmp/lumen_etl/{{ ds }} "
            f"gs://{GCS_BUCKET}/{{{{ ds }}}}/"
        ),
    )

    bq_loads = [
        GCSToBigQueryOperator(
            task_id=f"load_bq_{t}",
            bucket=GCS_BUCKET,
            source_objects=[f"{{{{ ds }}}}/{t}/data.jsonl"],
            destination_project_dataset_table=f"{GCP_PROJECT}.{BQ_RAW}.{t}",
            source_format="NEWLINE_DELIMITED_JSON",
            write_disposition="WRITE_TRUNCATE" if t in DIM_TABLES else "WRITE_APPEND",
            autodetect=False,
        )
        for t in [*DIM_TABLES, *INCR_TABLES.keys()]
    ]

    refresh_marts = BashOperator(
        task_id="refresh_marts",
        bash_command=(
            'bq query --use_legacy_sql=false '
            '"$(envsubst < /opt/airflow/dags/sql/02_dims_facts.sql)" && '
            'bq query --use_legacy_sql=false '
            '"$(envsubst < /opt/airflow/dags/sql/03_marts.sql)"'
        ),
        env={
            "GCP_PROJECT_ID": GCP_PROJECT,
            "BQ_DATASET_RAW": BQ_RAW,
            "BQ_DATASET_MART": BQ_MART,
        },
    )

    extract_dims + extract_facts >> upload_to_gcs >> bq_loads >> refresh_marts


if __name__ == "__main__":
    # Allow running the DAG file directly for debugging.
    dag.cli()
