# Lumen Commerce — end-to-end ecommerce analytics platform

**Application**
[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-2.0-D71F00?logo=sqlalchemy&logoColor=white)](https://www.sqlalchemy.org/)
[![Pydantic](https://img.shields.io/badge/Pydantic-v2-E92063?logo=pydantic&logoColor=white)](https://docs.pydantic.dev/)
[![Jinja](https://img.shields.io/badge/Jinja2-3.1-B41717?logo=jinja&logoColor=white)](https://jinja.palletsprojects.com/)

**Data**
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![Cube.dev](https://img.shields.io/badge/Cube.dev-semantic%20layer-FF6492)](https://cube.dev/)
[![Airflow](https://img.shields.io/badge/Apache%20Airflow-2.10-017CEE?logo=apacheairflow&logoColor=white)](https://airflow.apache.org/)
[![BigQuery](https://img.shields.io/badge/BigQuery-star%20schema-669DF6?logo=googlebigquery&logoColor=white)](https://cloud.google.com/bigquery)

**Analytics**
[![Chart.js](https://img.shields.io/badge/Chart.js-4-FF6384?logo=chartdotjs&logoColor=white)](https://www.chartjs.org/)
[![Looker Studio](https://img.shields.io/badge/Looker%20Studio-reports-4285F4?logo=looker&logoColor=white)](https://lookerstudio.google.com/)
[![Prophet](https://img.shields.io/badge/Prophet-forecasting-4267B2)](https://facebook.github.io/prophet/)

**Platform**
[![Docker](https://img.shields.io/badge/Docker-compose-2496ED?logo=docker&logoColor=white)](https://docs.docker.com/compose/)
[![Cloud Run](https://img.shields.io/badge/Cloud%20Run-deploy-4285F4?logo=googlecloud&logoColor=white)](https://cloud.google.com/run)
[![Ruff](https://img.shields.io/badge/lint-ruff-D7FF64?logo=ruff&logoColor=black)](https://docs.astral.sh/ruff/)

A working reference implementation showing the full path from transactional
OLTP application through to executive dashboards and ML-driven advanced
analytics. Built end-to-end so the same data flows from a real checkout into
the warehouse, into reports, into a forecasting model, and into a non-technical
business presentation.

## What's inside

| Layer | Stack | Path |
|-------|-------|------|
| Transactional app | FastAPI + SQLAlchemy + Jinja2 | `app/` |
| Storefront flow | Register/login, cart, checkout, order history | `app/api/pages.py`, `app/services/` |
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

Open <http://localhost:8000>. Sign in as `demo@lumen.com` / `demo12345` (the
seed prints the demo accounts) to browse, add to a cart and check out — the
resulting order lands in the same tables the dashboards read from.

The full step-by-step (with verify commands at every step) is in
[`RUNBOOK.md`](RUNBOOK.md). Run `make help` to see all targets.

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
