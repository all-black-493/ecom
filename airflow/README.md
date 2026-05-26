# Airflow orchestration

## DAG topology

```
postgres_to_bigquery_hourly (every hour)
    │
    ├── extract_dimensions    (full reload — small tables)
    ├── extract_facts         (incremental, by _updated_at / partition)
    └── refresh_marts         (CREATE OR REPLACE the SQL views)

postgres_to_bigquery_daily   (02:00 UTC)
    │
    └── full_reconciliation  (compare row counts, alert on drift)

forecast_retrain (03:00 UTC)
    │
    ├── pull_training_data   (90 days of mart_daily_revenue per category)
    ├── train_prophet        (one model per category + a top-line model)
    ├── write_forecast       (overwrite mart_demand_forecast partition)
    └── publish_to_app       (write app/static/forecast.json)
```

## Idempotency

Every task is idempotent. The DAG re-runs cleanly because:

- **Dimension extracts** are full reloads (small, cheap).
- **Fact extracts** delete the affected partition in BigQuery before re-inserting (delete-and-insert by `DATE(placed_at)`).
- **Marts** are `CREATE OR REPLACE VIEW` — no state.
- **Forecast** writes a single new run timestamp; old runs stay in the partition for back-testing.

## Why hourly + daily?

- **Hourly** runs the ETL with a 1-hour window — Looker Studio and Cube
  both stay close to real time. Cost is small because partitions are tiny.
- **Daily** runs a full reconciliation and refreshes anything that needs
  a longer-window look (cohort tables, LTV).

## Local dev

```bash
docker compose --profile airflow up airflow airflow-db
# http://localhost:8080  (admin/admin)
```

If you don't want to run Airflow locally, the DAG files double as
runnable Python — `python airflow/dags/etl_postgres_to_bigquery.py` will
execute the extract directly (helpful for debugging in your IDE).
