# Runbook — running everything, in order

There are three distinct *modes* you can run the project in. Pick the one
that matches what you want to verify, then follow the numbered steps.
Every step has a verification command — if the verify fails, **stop** and
fix that step before moving on.

| Mode | Time | What you verify |
|------|------|------------------|
| **A. Minimum local** | ~5 min | App, dashboards, REST APIs work against seeded Postgres |
| **B. Full local** (with Cube + Airflow) | ~15 min | Cube.dev queries flow; Airflow can list DAGs |
| **C. Production (GCP)** | ~30 min | BigQuery warehouse, Cloud Run app, Looker Studio reports, ML retrain |

---

## Prerequisites

* `docker` + `docker compose` (compose v2)
* `python` 3.11+
* `make`
* `curl` (used by `make smoke`)
* (Mode C only) `gcloud` CLI authenticated to a project where you have **Owner** or `roles/run.admin` + `roles/cloudsql.admin` + `roles/bigquery.admin`

Sanity check:

```bash
docker compose version           # 2.x or higher
python3 --version                # 3.11.x or higher
make --version                   # any
```

---

## A. Minimum local (5 minutes)

This gets you the app, the storefront, and both dashboards running against
seeded Postgres data. No GCP, no Cube, no Airflow.

### A1. Configure environment

```bash
cd ecom
make env
```

This copies `.env.example` to `.env`. For mode A you don't need to edit
anything — the defaults work for a local Docker Postgres.

**Verify:** `cat .env | head -5` shows real values, not just `${VAR}`.

### A2. Install Python deps

```bash
make install
```

Creates `.venv/`, installs FastAPI, SQLAlchemy, Faker, etc.

**Verify:** `.venv/bin/uvicorn --version` prints a version.

### A3. Start Postgres

```bash
make postgres
```

Brings up the `lumen-postgres` container and waits for the healthcheck.

**Verify:** `make shell` opens a `psql` prompt; `\dt` shows no tables yet
(expected — seeding creates them). Type `\q` to exit.

### A4. Create tables and seed realistic data

```bash
make seed
```

This runs `scripts/seed.py --reset` — drops the schema, recreates it, and
loads 1,000 customers, 120 products, ~25k orders, 40k events,
2,500 abandoned carts. Takes ~60–90 seconds.

**Verify:** `make shell` then `SELECT COUNT(*) FROM orders;` should return
roughly 22,000–28,000.

### A5. Run the app

In a new terminal (keep this one running):

```bash
make app
```

**Verify:** open these in a browser:

| URL | What you should see |
|-----|----------------------|
| http://localhost:8000/ | Storefront home with category cards |
| http://localhost:8000/catalog | Grid of products |
| http://localhost:8000/dashboards | Two tiles: Sales, Inventory |
| http://localhost:8000/dashboards/sales | 4 KPIs, 4 charts, top-10 table |
| http://localhost:8000/dashboards/inventory | Funnel, abandonment, stockout table, forecast chart |
| http://localhost:8000/docs | FastAPI Swagger UI |

### A6. Smoke-test every endpoint

In a third terminal:

```bash
make smoke
```

Hits 21 endpoints and reports pass/fail. All must be green for mode A
to be considered working.

### A7. (optional) Run the ML forecast

```bash
make forecast
```

Trains the Prophet model on the seeded Postgres data, writes
`app/static/forecast.json` and `ml/forecast_metrics.json`. The inventory
dashboard chart will then show your real-data forecast instead of the
pre-shipped sample.

**Verify:** `cat ml/forecast_metrics.json` shows MAPE under ~0.15.

### A8. Tear down

```bash
make down           # stops containers, keeps the data volume
# or
make nuke           # stops and deletes data — fresh start next time
```

---

## B. Full local — adds Cube.dev and Airflow

Do mode A first. Then:

### B1. Start Cube.dev

```bash
make cube
```

**Verify:** open http://localhost:4000 — Cube playground opens with the
five models (Orders, OrderItems, Products, Customers, Carts) listed in
the left sidebar. Run the `Orders.revenue` measure to verify it talks to
Postgres.

After Cube starts, the in-app **Sales dashboard** will use Cube as its
primary data source automatically (with REST-API fallback if Cube fails).

### B2. Start Airflow

```bash
make airflow
```

This brings up two containers: `lumen-airflow-db` (its own Postgres) and
`lumen-airflow` (webserver + scheduler in `airflow standalone` mode).

**Verify:** http://localhost:8080 — login `admin` / `admin`. You should
see two DAGs:

* `etl_postgres_to_bigquery_hourly`
* `forecast_retrain_daily`

Both will be **paused** by default and will error if you try to run them
without GCP credentials. They're correctly registered — that's the goal of
mode B.

### B3. Tear down (Airflow is heavy)

```bash
make down
```

---

## C. Production (Google Cloud)

The cloud deployment hits four services: Cloud Run, Cloud SQL, BigQuery,
and Looker Studio. Optionally Cloud Composer for Airflow.

### C1. Set up GCP project

```bash
export PROJECT_ID=my-lumen-proj         # pick a globally unique name
export REGION=us-central1
gcloud auth login
gcloud projects create "$PROJECT_ID" --set-as-default || gcloud config set project "$PROJECT_ID"

gcloud services enable \
  run.googleapis.com \
  sqladmin.googleapis.com \
  bigquery.googleapis.com \
  artifactregistry.googleapis.com \
  iamcredentials.googleapis.com \
  cloudbuild.googleapis.com \
  cloudscheduler.googleapis.com
```

### C2. Provision Cloud SQL (Postgres)

```bash
gcloud sql instances create lumen-pg \
  --database-version=POSTGRES_16 --tier=db-g1-small \
  --region="$REGION" --storage-size=10 --storage-type=SSD
gcloud sql databases create lumen --instance=lumen-pg
gcloud sql users create lumen --instance=lumen-pg --password=CHOOSE_A_STRONG_PASSWORD

# Build the DATABASE_URL for your secrets store
echo "postgresql+psycopg2://lumen:CHOOSE_A_STRONG_PASSWORD@/lumen?host=/cloudsql/$PROJECT_ID:$REGION:lumen-pg" \
  | gcloud secrets create lumen-database-url --data-file=-
```

### C3. Provision BigQuery (run the DDL)

```bash
make bq-init PROJECT_ID=$PROJECT_ID
```

**Verify:** `bq ls --project_id=$PROJECT_ID` shows datasets `lumen_raw`
and `lumen_mart`.

### C4. Build & push the container image

```bash
gcloud artifacts repositories create lumen \
  --repository-format=docker --location=$REGION
make image PROJECT_ID=$PROJECT_ID REGION=$REGION
```

### C5. Create the secrets Cloud Run will reference

```bash
echo -n "production-app-secret-CHANGE-ME" | gcloud secrets create lumen-app-secret --data-file=-
echo -n "production-cube-secret-CHANGE-ME" | gcloud secrets create lumen-cube-secret --data-file=-
# lumen-database-url was already created in C2

# Allow Cloud Run's runtime service account to read these
SA=lumen-runtime@$PROJECT_ID.iam.gserviceaccount.com
gcloud iam service-accounts create lumen-runtime
for s in lumen-app-secret lumen-cube-secret lumen-database-url; do
  gcloud secrets add-iam-policy-binding $s \
    --member="serviceAccount:$SA" --role=roles/secretmanager.secretAccessor
done
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:$SA" --role=roles/cloudsql.client
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:$SA" --role=roles/bigquery.dataViewer
```

### C6. Seed Cloud SQL once

Easiest: open a one-shot Cloud SQL Auth Proxy session locally and run the
existing seed script against it.

```bash
cloud-sql-proxy "$PROJECT_ID:$REGION:lumen-pg" &
DATABASE_URL="postgresql+psycopg2://lumen:CHOOSE_A_STRONG_PASSWORD@127.0.0.1:5432/lumen" \
  .venv/bin/python scripts/seed.py --reset
kill %1
```

### C7. Deploy the app

```bash
make deploy PROJECT_ID=$PROJECT_ID REGION=$REGION
```

The deploy script prints the public URL when done.

**Verify:** `curl https://<url>/healthz` → `{"status":"ok"}`. Then run
`make smoke APP_URL=https://<url>` (or `bash scripts/smoke.sh https://<url>`)
— all green.

### C8. Schedule the ETL + forecast jobs

Two cheap options:

**Option A — Cloud Run Jobs + Cloud Scheduler** (recommended, ~$0/mo)

```bash
gcloud run jobs deploy lumen-forecast \
  --image $REGION-docker.pkg.dev/$PROJECT_ID/lumen/lumen-app:latest \
  --region $REGION --service-account $SA \
  --command python --args="ml/run_forecast.py,--horizon,30" \
  --set-secrets DATABASE_URL=lumen-database-url:latest

gcloud scheduler jobs create http forecast-nightly \
  --schedule="0 3 * * *" --time-zone="UTC" --location="$REGION" \
  --uri="https://run.googleapis.com/v2/projects/$PROJECT_ID/locations/$REGION/jobs/lumen-forecast:run" \
  --http-method=POST --oauth-service-account-email=$SA
```

**Option B — Cloud Composer** (managed Airflow; ~$300/mo)

```bash
gcloud composer environments create lumen-orch \
  --location=$REGION --image-version=composer-3-airflow-2.10.3
gcloud composer environments storage dags import \
  --environment=lumen-orch --location=$REGION --source=airflow/dags
```

### C9. Publish Looker Studio reports

Looker Studio is hosted UI — there's no CLI. Follow
[`docs/dashboards/looker-studio/README.md`](docs/dashboards/looker-studio/README.md):

1. Open https://lookerstudio.google.com → New Report
2. Connect data → BigQuery → `$PROJECT_ID.lumen_mart.ls_v_executive_daily`
3. Apply `theme.json` (Resource → Theme → upload).
4. Build the panels per the spec (~20 minutes per report).
5. Share publicly (View only) → copy the link → paste into `deploy/README.md`.

### C10. Custom domain (optional)

```bash
gcloud beta run domain-mappings create --service=lumen-app \
  --domain=shop.example.com --region=$REGION
```

Add the verification CNAME at your DNS provider as instructed.

---

## Environment variables

Here is the complete list of env vars the project uses. **Bold** vars are
the only ones you must change before running locally.

### Local development (mode A & B)

The `.env` file (created by `make env`) is read by both the FastAPI app
and `docker-compose`.

| Variable | Default in `.env.example` | Purpose | Must change locally? |
|----------|---------------------------|---------|----------------------|
| `APP_ENV` | `local` | Tagged into logs | No |
| `APP_SECRET` | `change-me-in-prod` | Cookie signing, future auth | No (mode A) |
| `APP_PORT` | `8000` | Where uvicorn listens | No |
| `POSTGRES_HOST` | `localhost` | Used by host-network connections | No |
| `POSTGRES_PORT` | `5432` | | No |
| `POSTGRES_DB` | `lumen` | | No |
| `POSTGRES_USER` | `lumen` | | No |
| `POSTGRES_PASSWORD` | `lumen` | | No |
| `DATABASE_URL` | `postgresql+psycopg2://lumen:lumen@localhost:5432/lumen` | App connection string | No |
| `CUBE_API_SECRET` | `cube-secret-change-me` | Shared between Cube and the FastAPI page templates | No (mode A); No (mode B local) |
| `CUBEJS_DB_*` | mirrors Postgres vars | Cube's own DB connection | No |
| `CUBEJS_API_URL` | `http://localhost:4000/cubejs-api/v1` | Where the dashboards call Cube | No |
| `CUBEJS_DEV_MODE` | `true` | Loosens auth in Cube playground | No |
| `GCP_PROJECT_ID` | `your-gcp-project` | Used by the ETL DAG and ML job | **Only if running mode C or `make bq-init`** |
| `BQ_DATASET_RAW` | `lumen_raw` | | No |
| `BQ_DATASET_MART` | `lumen_mart` | | No |
| `GOOGLE_APPLICATION_CREDENTIALS` | `./deploy/gcp-sa.json` | Path to service-account JSON for ETL | **Only for mode C / Airflow** |
| `AIRFLOW__*` | various | Airflow self-config | No |

**TL;DR for mode A:** copy `.env.example` to `.env` and run. Don't change anything.

### Production (mode C)

In production, **no `.env` file** is shipped. Cloud Run gets its env vars from
secrets and the service.yaml. Here's the mapping:

| Variable | Source in production | Used by |
|----------|----------------------|---------|
| `APP_ENV` | hard-coded `production` in service.yaml | FastAPI |
| `APP_SECRET` | Secret Manager `lumen-app-secret` | FastAPI |
| `DATABASE_URL` | Secret Manager `lumen-database-url` | FastAPI |
| `CUBEJS_API_URL` | hard-coded `https://cube-lumen.example.com/...` | Sales dashboard |
| `CUBE_API_SECRET` | Secret Manager `lumen-cube-secret` | FastAPI page templates |
| `GCP_PROJECT_ID` | hard-coded in service.yaml | ETL job, ML job |
| `BQ_DATASET_RAW` / `BQ_DATASET_MART` | hard-coded in service.yaml | ETL job, ML job |
| GCP credentials | Cloud Run runtime service account (no JSON file) | ETL job, ML job |
| `PORT` | injected by Cloud Run | uvicorn |

There is **nothing on your laptop** that needs to be different for production
beyond the `PROJECT_ID` and `REGION` you pass on the `make deploy` command line.

---

## Troubleshooting one-liners

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `make seed` hangs | postgres not healthy yet | `make postgres` first, wait for "is ready" |
| Dashboards show empty charts | seed not run | `make seed` |
| "Connection refused" on `:5432` | Postgres container died | `make logs` then `make postgres` |
| Cube playground is empty | Cube can't reach Postgres | check Cube container uses service name `postgres` not `localhost` |
| Forecast chart says "no forecast file" | `make forecast` never ran | run it, or just keep the pre-shipped sample |
| Airflow DAGs marked broken | missing GCP creds | expected in mode B — the DAGs import is OK, runs need creds |
| `make deploy` says "permission denied" | service account missing roles | run the IAM commands in C5 again |
