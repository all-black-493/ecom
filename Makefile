# --------------------------------------------------------------------- Lumen
# One-shot targets for local development and production deployment.
# Run `make help` to list everything.

SHELL := /usr/bin/env bash
.SHELLFLAGS := -eu -o pipefail -c
.DEFAULT_GOAL := help

# ----------------------------------------------------------------- variables
PYTHON      ?= python3
VENV        ?= .venv
PIP         := $(VENV)/bin/pip
PY          := $(VENV)/bin/python
UVICORN     := $(VENV)/bin/uvicorn
PYTEST      := $(VENV)/bin/pytest
RUFF        := $(VENV)/bin/ruff

APP_HOST    ?= 0.0.0.0
APP_PORT    ?= 8000
APP_URL     := http://localhost:$(APP_PORT)
CUBE_URL    := http://localhost:4000
LOCUST_HOST ?= http://localhost:$(APP_PORT)

# Cloud Run defaults — override on the make command line or in .envrc.
# The ?= form means these are only set if they aren't already in the env.
PROJECT_ID  ?= my-lumen-proj
REGION      ?= us-central1
SA          ?= lumen-runtime@$(PROJECT_ID).iam.gserviceaccount.com

# Detect docker compose v2 vs v1
COMPOSE     := $(shell docker compose version >/dev/null 2>&1 && echo "docker compose" || echo "docker-compose")

# ------------------------------------------------------------- meta targets
.PHONY: help
help:  ## list available targets
	@awk 'BEGIN {FS = ":.*##"; printf "\nUsage: \033[1mmake <target>\033[0m\n\nTargets:\n"} \
	  /^[a-zA-Z_-]+:.*##/ {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)
	@echo

# -------------------------------------------------------------- environment
.PHONY: env
env:  ## copy .env.example -> .env if missing
	@[ -f .env ] || (cp .env.example .env && echo "wrote .env (review it before running)")
	@grep -E '^(DATABASE_URL|APP_SECRET|GCP_PROJECT_ID)=' .env || true

$(VENV)/bin/python:
	$(PYTHON) -m venv $(VENV)

.PHONY: install
install: $(VENV)/bin/python  ## install Python deps into a local venv
	$(PIP) install --upgrade pip
	$(PIP) install -e ".[dev]"

.PHONY: install-ml
install-ml: install  ## install the ML extras (Prophet, pandas-gbq, etc.)
	$(PIP) install -e ".[ml]"

# ----------------------------------------------------------------- services
.PHONY: postgres
postgres:  ## start only postgres in the background
	$(COMPOSE) up -d postgres
	@echo "waiting for postgres healthcheck…"
	@until $(COMPOSE) exec -T postgres pg_isready -U lumen >/dev/null 2>&1; do sleep 1; done
	@echo "postgres is ready on :5432"

.PHONY: cube
cube:  ## start Cube.dev in the background
	$(COMPOSE) up -d cube
	@echo "Cube playground: $(CUBE_URL)"

.PHONY: airflow
airflow:  ## start Airflow (and its metadata db) — heavy
	$(COMPOSE) --profile airflow up -d airflow-db airflow
	@echo "Airflow UI: http://localhost:8080  (admin / admin)"

.PHONY: up
up: postgres cube  ## start postgres + cube

.PHONY: down
down:  ## stop and remove all containers (data preserved)
	$(COMPOSE) --profile airflow down

.PHONY: nuke
nuke:  ## stop and ERASE all containers AND volumes (destructive)
	$(COMPOSE) --profile airflow down -v

# -------------------------------------------------------------- application
.PHONY: seed
seed: install postgres  ## create tables and seed realistic data
	DATABASE_URL=$$(grep ^DATABASE_URL .env | cut -d= -f2-) \
	  $(PY) scripts/seed.py --reset

.PHONY: app
app: install  ## run FastAPI dev server (reload on save)
	$(UVICORN) app.main:app --reload --host $(APP_HOST) --port $(APP_PORT)

.PHONY: dev
dev: env up seed  ## first-time bootstrap: env, services, schema, seed
	@echo
	@echo "▸ Ready. Now run:    make app"
	@echo "▸ Open:              $(APP_URL)"
	@echo "▸ Dashboards:        $(APP_URL)/dashboards"
	@echo "▸ Cube playground:   $(CUBE_URL)"

# --------------------------------------------------------- ML / forecasting
.PHONY: forecast
forecast: install-ml  ## train the Prophet demand model and publish forecast.json
	DATABASE_URL=$$(grep ^DATABASE_URL .env | cut -d= -f2-) \
	  $(PY) ml/run_forecast.py --horizon 30 --history-days 540
	@echo
	@echo "wrote app/static/forecast.json"
	@echo "metrics: ml/forecast_metrics.json"

# ------------------------------------------------------------------- tests
.PHONY: smoke
smoke:  ## hit every endpoint to verify a running stack
	@bash scripts/smoke.sh $(APP_URL)

.PHONY: loadtest
loadtest: install  ## start the Locust load generator (web UI on :8089)
	@echo "▸ Locust UI:    http://localhost:8089"
	@echo "▸ Target host:  $(LOCUST_HOST)"
	@echo "▸ Suggested:    Start with 20 users, spawn rate 2/sec"
	$(VENV)/bin/locust -f scripts/locustfile.py --host=$(LOCUST_HOST)

.PHONY: loadtest-headless
loadtest-headless: install  ## one-shot 5-min load run (no UI). Override USERS/RATE/TIME on the command line.
	$(VENV)/bin/locust -f scripts/locustfile.py --host=$(LOCUST_HOST) \
	  --users $(or $(USERS),20) --spawn-rate $(or $(RATE),2) --run-time $(or $(TIME),5m) --headless

.PHONY: test
test: install  ## run pytest
	$(PYTEST) -q

.PHONY: lint
lint: install  ## ruff check
	$(RUFF) check .

.PHONY: format
format: install  ## ruff format
	$(RUFF) format .

# --------------------------------------------------------- warehouse / BQ
.PHONY: bq-load
bq-load: install-ml  ## bulk-copy Cloud SQL data into BigQuery lumen_raw (one-shot; runs through cloud-sql-proxy)
	@test -n "$(PROJECT_ID)" || (echo "ERROR: set PROJECT_ID=…"; exit 1)
	@command -v cloud-sql-proxy >/dev/null || (echo "install cloud-sql-proxy first"; exit 1)
	@echo "▸ Starting Cloud SQL proxy in background…"
	cloud-sql-proxy "$(PROJECT_ID):$(REGION):lumen-pg" & echo $$! > /tmp/lumen-proxy.pid; sleep 3
	@echo "▸ Reading DB password (input hidden)…"
	@PW=$$($(PY) -c "import getpass; print(getpass.getpass('DB password: '), end='')") ; \
	  DATABASE_URL="postgresql+psycopg2://lumen:$$PW@127.0.0.1:5432/lumen" \
	  GCP_PROJECT_ID=$(PROJECT_ID) BQ_DATASET_RAW=lumen_raw \
	  $(PY) scripts/bootstrap_bigquery.py ; \
	  kill $$(cat /tmp/lumen-proxy.pid) 2>/dev/null || true ; rm -f /tmp/lumen-proxy.pid
	@echo "▸ Done. Refresh your Data Studio report."

.PHONY: bq-init
bq-init:  ## create BigQuery datasets and run DDL (requires gcloud auth + PROJECT_ID)
	@test -n "$(PROJECT_ID)" || (echo "ERROR: set PROJECT_ID=… on the command line"; exit 1)
	bq --location=US mk --dataset --force $(PROJECT_ID):lumen_raw
	bq --location=US mk --dataset --force $(PROJECT_ID):lumen_mart
	GCP_PROJECT_ID=$(PROJECT_ID) BQ_DATASET_RAW=lumen_raw BQ_DATASET_MART=lumen_mart \
	  envsubst < warehouse/sql/01_raw.sql       | bq query --use_legacy_sql=false --project_id=$(PROJECT_ID)
	GCP_PROJECT_ID=$(PROJECT_ID) BQ_DATASET_RAW=lumen_raw BQ_DATASET_MART=lumen_mart \
	  envsubst < warehouse/sql/02_dims_facts.sql | bq query --use_legacy_sql=false --project_id=$(PROJECT_ID)
	GCP_PROJECT_ID=$(PROJECT_ID) BQ_DATASET_RAW=lumen_raw BQ_DATASET_MART=lumen_mart \
	  envsubst < warehouse/sql/03_marts.sql     | bq query --use_legacy_sql=false --project_id=$(PROJECT_ID)

# ----------------------------------------------------------- Cloud deploy
.PHONY: image
image:  ## build & push the container image to Artifact Registry
	@test -n "$(PROJECT_ID)" || (echo "ERROR: set PROJECT_ID=…"; exit 1)
	$(eval SHA := $(shell git rev-parse --short HEAD 2>/dev/null || date +%s))
	$(eval REPO := $(REGION)-docker.pkg.dev/$(PROJECT_ID)/lumen/lumen-app)
	gcloud builds submit \
	  --project=$(PROJECT_ID) \
	  --config=deploy/cloudbuild.yaml \
	  --substitutions=_IMAGE=$(REPO):$(SHA),_IMAGE_LATEST=$(REPO):latest,_IMAGE_REPO=$(REPO) \
	  .
	@echo "built: $(REPO):$(SHA)"

.PHONY: deploy
deploy:  ## deploy app to Cloud Run (run after `make image`)
	@test -n "$(PROJECT_ID)" || (echo "ERROR: set PROJECT_ID=…"; exit 1)
	PROJECT_ID=$(PROJECT_ID) REGION=$(REGION) bash deploy/cloud-run/deploy.sh

# ----------------------------------------------------------- conveniences
.PHONY: shell
shell: postgres  ## psql into the running postgres
	$(COMPOSE) exec postgres psql -U lumen -d lumen

.PHONY: logs
logs:  ## tail logs for all services
	$(COMPOSE) logs -f --tail=100

.PHONY: clean
clean:  ## remove pyc, build artifacts, forecast outputs
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	rm -rf .pytest_cache .ruff_cache build dist *.egg-info
	rm -f ml/forecast_metrics.json ml/forecast_categories.csv
