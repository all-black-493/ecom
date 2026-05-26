FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

# Build toolchain stays small: gcc for psycopg2; libpq for runtime.
# Prophet needs no extra system packages — its wheels bundle cmdstanpy.
RUN apt-get update \
 && apt-get install -y --no-install-recommends gcc libpq-dev curl ca-certificates \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /code
COPY pyproject.toml ./

# Install both web and ML deps so the same image can run uvicorn OR the
# Prophet forecast job. Adds ~250 MB (mostly numpy/pandas/prophet); fine
# for our scale. If you want a slimmer web-only image later, split this
# into Dockerfile + Dockerfile.ml and build two tags.
RUN pip install --upgrade pip && pip install -e ".[ml]"

COPY app ./app
COPY scripts ./scripts
COPY ml ./ml

EXPOSE 8000

# Default command is the web app. The forecast job overrides it via
#   gcloud run jobs deploy --command=python --args="ml/run_forecast.py,..."
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 2"]
