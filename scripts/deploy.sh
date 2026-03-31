#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-example-gcp-project}"
REGION="${REGION:-us-central1}"
DATASET="${DATASET:-github_access_audit}"
ORG="${ORG:-example-org}"
SERVICE_NAME="${SERVICE_NAME:-github-access-sync}"
SECRET_NAME="${SECRET_NAME:-github-access-token}"
RUNTIME_SA_NAME="${RUNTIME_SA_NAME:-github-access-sync-sa}"
SCHEDULER_SA_NAME="${SCHEDULER_SA_NAME:-github-access-sync-scheduler}"
SCHEDULER_JOB_NAME="${SCHEDULER_JOB_NAME:-github-access-sync-daily}"
SCHEDULER_TIMEZONE="${SCHEDULER_TIMEZONE:-Etc/UTC}"
SCHEDULER_SCHEDULE="${SCHEDULER_SCHEDULE:-0 8 * * *}"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNTIME_SA_EMAIL="${RUNTIME_SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
SCHEDULER_SA_EMAIL="${SCHEDULER_SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

bash "$ROOT_DIR/scripts/bootstrap_gcp.sh"

gcloud run deploy "$SERVICE_NAME" \
  --project "$PROJECT_ID" \
  --region "$REGION" \
  --source "$ROOT_DIR" \
  --service-account "$RUNTIME_SA_EMAIL" \
  --timeout 900 \
  --no-allow-unauthenticated \
  --set-env-vars "ORG=${ORG},BQ_PROJECT=${PROJECT_ID},BQ_DATASET=${DATASET},BQ_LOCATION=${REGION},EXPORT_SCRIPT_PATH=/app/scripts/export_all_access.sh" \
  --set-secrets "GH_TOKEN=${SECRET_NAME}:latest"

SERVICE_URL="$(gcloud run services describe "$SERVICE_NAME" \
  --project "$PROJECT_ID" \
  --region "$REGION" \
  --format='value(status.url)')"

gcloud run services add-iam-policy-binding "$SERVICE_NAME" \
  --project "$PROJECT_ID" \
  --region "$REGION" \
  --member="serviceAccount:${SCHEDULER_SA_EMAIL}" \
  --role="roles/run.invoker" \
  --condition=None \
  --quiet >/dev/null

if gcloud scheduler jobs describe "$SCHEDULER_JOB_NAME" --project "$PROJECT_ID" --location "$REGION" >/dev/null 2>&1; then
  gcloud scheduler jobs update http "$SCHEDULER_JOB_NAME" \
    --project "$PROJECT_ID" \
    --location "$REGION" \
    --schedule "$SCHEDULER_SCHEDULE" \
    --time-zone "$SCHEDULER_TIMEZONE" \
    --attempt-deadline 900s \
    --uri "${SERVICE_URL}/sync" \
    --http-method POST \
    --oidc-service-account-email "$SCHEDULER_SA_EMAIL" \
    --oidc-token-audience "$SERVICE_URL"
else
  gcloud scheduler jobs create http "$SCHEDULER_JOB_NAME" \
    --project "$PROJECT_ID" \
    --location "$REGION" \
    --schedule "$SCHEDULER_SCHEDULE" \
    --time-zone "$SCHEDULER_TIMEZONE" \
    --attempt-deadline 900s \
    --uri "${SERVICE_URL}/sync" \
    --http-method POST \
    --oidc-service-account-email "$SCHEDULER_SA_EMAIL" \
    --oidc-token-audience "$SERVICE_URL"
fi

echo "Deployment complete"
echo "Cloud Run URL: ${SERVICE_URL}"
echo "Scheduler job: ${SCHEDULER_JOB_NAME}"
