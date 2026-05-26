# Production deployment

We deploy each layer to a GCP-native service so the whole pipeline runs
without self-managing servers:

| Layer       | GCP service                | Why                                 |
|-------------|----------------------------|--------------------------------------|
| FastAPI app | **Cloud Run**              | scale-to-zero; HTTPS by default      |
| Postgres    | **Cloud SQL** (Postgres 16)| managed backups, replicas, IAM auth |
| Cube.dev    | **Cloud Run** (separate svc)| same lifecycle as app, low traffic   |
| Airflow     | **Cloud Composer 3** (or VM)| managed Airflow; or self-host        |
| Warehouse   | **BigQuery**               | already serverless; pay-per-query    |
| Reports     | **Looker Studio**          | hosted; connects to BigQuery via OAuth |
| ML training | **Cloud Run Jobs** (cron)  | one-shot, no idle cost               |

## End-to-end runbook

### 1. Bootstrap once

```bash
export PROJECT_ID=my-lumen-proj
export REGION=us-central1
gcloud projects create $PROJECT_ID || true
gcloud config set project $PROJECT_ID
gcloud services enable \
  run.googleapis.com \
  sqladmin.googleapis.com \
  bigquery.googleapis.com \
  artifactregistry.googleapis.com \
  composer.googleapis.com \
  iamcredentials.googleapis.com
```

### 2. Provision Postgres

```bash
gcloud sql instances create lumen-pg \
  --database-version=POSTGRES_16 \
  --tier=db-g1-small \
  --region=$REGION \
  --storage-type=SSD --storage-size=10
gcloud sql databases create lumen --instance=lumen-pg
gcloud sql users create lumen --instance=lumen-pg --password='use a real one'
```

### 3. Provision BigQuery

```bash
bq mk --location=US lumen_raw
bq mk --location=US lumen_mart
# substitute project id in DDL then run
envsubst < warehouse/sql/01_raw.sql           | bq query --use_legacy_sql=false
envsubst < warehouse/sql/02_dims_facts.sql    | bq query --use_legacy_sql=false
envsubst < warehouse/sql/03_marts.sql         | bq query --use_legacy_sql=false
```

### 4. Push image & deploy

```bash
gcloud artifacts repositories create lumen --repository-format=docker --location=$REGION
bash deploy/cloud-run/deploy.sh
```

### 5. Wire Airflow

For Composer:

```bash
gcloud composer environments create lumen-orch \
  --location=$REGION --image-version=composer-3-airflow-2.10.3
gcloud composer environments storage dags import \
  --environment=lumen-orch --location=$REGION --source=airflow/dags
```

Set Airflow connections:

* `lumen_postgres` → Cloud SQL connection via Cloud SQL Auth Proxy
* `google_cloud_default` → service account JSON with BigQuery + GCS roles

### 6. Train initial forecast

```bash
gcloud run jobs deploy lumen-forecast \
  --image=$REGION-docker.pkg.dev/$PROJECT_ID/lumen/lumen-app:latest \
  --command=python --args="ml/run_forecast.py,--horizon,30"
gcloud run jobs execute lumen-forecast --wait
```

### 7. Publish Looker Studio reports

Follow `docs/dashboards/looker-studio/README.md` then paste the resulting
URLs back into the app footer.

## Cost envelope (rough, US-central, low traffic)

| Item               | Monthly USD |
|--------------------|------------|
| Cloud Run (scale-to-zero, ~10k req/day) | $1–5 |
| Cloud SQL db-g1-small (24/7) | $25 |
| BigQuery (under 1 TB/month) | $0–5 |
| Composer (small) | $300 — consider Cloud Run Jobs + Cloud Scheduler for < $5 |
| Cube.dev Cloud Run | $1–5 |
| **Total realistic** | **$30–40** (replace Composer with Cloud Scheduler) |

## CI / GitHub Actions

`.github/workflows/deploy.yml` is included for completeness — pushes to
`main` build the image, run `pytest`, and deploy on green.
