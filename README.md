# Lumen Commerce — end-to-end ecommerce analytics platform

A working reference implementation showing the full path from transactional
OLTP application through to executive dashboards and ML-driven advanced
analytics. Built end-to-end so the same data flows from a real checkout into
the warehouse, into reports, into a forecasting model, and into a non-technical
business presentation.

## What's inside

| Layer | Stack | Path |
|-------|-------|------|
| Transactional app | FastAPI + SQLAlchemy + Jinja2 | `app/` |
| OLTP database | PostgreSQL 16 | `app/models/`, `scripts/seed.py` |
| Seed data | Faker (1k customers, 500 SKUs, 25k orders) | `scripts/seed.py` |
| Semantic layer | Cube.dev | `cube/` |
| In-app dashboards | Cube.js + Chart.js, served via FastAPI | `app/templates/dashboards/` |
| Warehouse | Google BigQuery (star schema) | `warehouse/sql/` |
| Orchestration | Apache Airflow 2 | `airflow/dags/` |
| BI / reports | Looker Studio (config + SQL views) | `docs/dashboards/looker-studio/` |
| Advanced analytics | Prophet demand forecasting | `ml/` |
| Deployment | Docker + Cloud Run / Railway | `deploy/` |
| Business presentation | HTML reveal-style deck | `docs/presentation/` |

## Quick start (local)

```bash
make dev      # env + postgres + cube + seed
make app      # in a new terminal
make smoke    # in a third terminal — green = working
```

Open <http://localhost:8000>. The full step-by-step (with verify
commands at every step) is in [`RUNBOOK.md`](RUNBOOK.md). Run
`make help` to see all targets.

## Architecture

```
       ┌────────────┐   sync     ┌──────────────┐    Airflow     ┌────────────┐
Users ─►   FastAPI  │◄──────────►│  PostgreSQL  │ ─────ETL──────►│  BigQuery  │
       │  (orders,  │            │   (OLTP)     │   (hourly)     │   (OLAP)   │
       │  catalog,  │            └──────────────┘                └─────┬──────┘
       │  cart, …)  │                   │                              │
       └────┬───────┘                   │ Cube.dev reads OLTP          │
            │                           │ live for in-app charts       ▼
            │                           ▼                       ┌────────────┐
            │                    ┌──────────────┐               │   Looker   │
            └────────────────────►   Cube.dev   │               │   Studio   │
                in-app dashboards│  (semantic)  │               └────────────┘
                                 └──────────────┘
                                                                        ▲
                                                                        │
                                                  ┌──────────────┐      │
                                                  │  Prophet ML  ├──────┘
                                                  │  forecasts   │  writes back
                                                  └──────────────┘
```

The OLTP database is the source of truth. Cube.dev sits over it for
low-latency in-app dashboards (a Cube semantic model is reused across both
the in-app charts and the analyst layer). Airflow ships daily snapshots to
BigQuery where Looker Studio handles long-horizon reporting and Prophet
produces demand forecasts that are written back into BigQuery and surfaced
in the same dashboards.

## Documentation index

- [`docs/analytics-questions.md`](docs/analytics-questions.md) — the 18 questions this platform answers
- [`docs/dashboard-design.md`](docs/dashboard-design.md) — information-design principles applied to each report
- [`docs/dashboards/`](docs/dashboards/) — wire-frames and dashboard specs
- [`docs/presentation/`](docs/presentation/) — business-user storytelling deck
- [`warehouse/README.md`](warehouse/README.md) — star schema, grain, late-arriving rows
- [`airflow/README.md`](airflow/README.md) — DAG topology, idempotency notes
- [`ml/README.md`](ml/README.md) — forecasting methodology, evaluation
- [`deploy/README.md`](deploy/README.md) — production deployment runbook
