#!/usr/bin/env bash
# Deploys Lumen Commerce to Google Cloud Run + Cloud SQL.
#
# Prerequisites (one-time, run interactively):
#   gcloud auth login
#   gcloud config set project $PROJECT_ID
#   gcloud services enable run.googleapis.com sqladmin.googleapis.com \
#     bigquery.googleapis.com artifactregistry.googleapis.com composer.googleapis.com
#   gcloud sql instances create lumen-pg --database-version=POSTGRES_16 \
#     --tier=db-f1-micro --region=$REGION
#   gcloud sql databases create lumen --instance=lumen-pg
#   gcloud secrets create lumen-database-url --data-file=- <<< "$DATABASE_URL"
#
# Then this script is idempotent and safe to re-run on each deploy.

set -euo pipefail
: "${PROJECT_ID:?must export PROJECT_ID}"
: "${REGION:=us-central1}"
: "${REPO:=lumen}"
: "${INSTANCE_ID:=lumen-pg}"   # Cloud SQL instance name — override if you used a different one
: "${IMAGE:=$REGION-docker.pkg.dev/$PROJECT_ID/$REPO/lumen-app:$(git rev-parse --short HEAD 2>/dev/null || echo latest)}"

echo "▸ Building image $IMAGE"
REPO="${REGION}-docker.pkg.dev/${PROJECT_ID}/lumen/lumen-app"
gcloud builds submit \
  --project="$PROJECT_ID" \
  --config=deploy/cloudbuild.yaml \
  --substitutions="_IMAGE=$IMAGE,_IMAGE_LATEST=$REPO:latest,_IMAGE_REPO=$REPO" \
  .

# Resolve :latest to its immutable digest. This is critical — without it,
# the substituted service.yaml is byte-identical on every deploy (because
# $IMAGE is always ":latest"), so `gcloud run services replace` treats
# the spec as unchanged and silently skips creating a new revision.
echo "▸ Resolving :latest to a content digest"
DIGEST=$(gcloud artifacts docker images describe "${REPO}:latest" \
  --format='value(image_summary.digest)')
IMAGE_PINNED="${REPO}@${DIGEST}"
echo "  Pinned to ${IMAGE_PINNED}"

echo "▸ Substituting placeholders in service.yaml"
SERVICE_FILE=$(mktemp)
# Substitute INSTANCE_ID FIRST so the more general PROJECT_ID/REGION subs that
# follow don't pre-mangle the connection-name string (which contains both).
# Note: image reference uses the digest (IMAGE_PINNED), not the tag.
sed -e "s|INSTANCE_ID|$INSTANCE_ID|g" \
    -e "s|REGION-docker.pkg.dev/PROJECT_ID/lumen/lumen-app:latest|$IMAGE_PINNED|g" \
    -e "s|PROJECT_ID|$PROJECT_ID|g" \
    -e "s|REGION|$REGION|g" \
    deploy/cloud-run/service.yaml > "$SERVICE_FILE"

echo "▸ Deploying"
gcloud run services replace "$SERVICE_FILE" --region "$REGION"
gcloud run services add-iam-policy-binding lumen-app --region "$REGION" \
    --member=allUsers --role=roles/run.invoker || true

URL=$(gcloud run services describe lumen-app --region "$REGION" --format='value(status.url)')
echo "▸ Deployed: $URL"
