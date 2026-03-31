#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-example-gcp-project}"
REGION="${REGION:-us-central1}"
DATASET="${DATASET:-github_access_audit}"
SERVICE_NAME="${SERVICE_NAME:-github-access-sync}"
RUNTIME_SA_NAME="${RUNTIME_SA_NAME:-github-access-sync-sa}"
SCHEDULER_SA_NAME="${SCHEDULER_SA_NAME:-github-access-sync-scheduler}"
SECRET_NAME="${SECRET_NAME:-github-access-token}"
GH_PAT="${GH_PAT:-}"
PROJECT_NUMBER="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')"
SCHEDULER_SERVICE_AGENT="service-${PROJECT_NUMBER}@gcp-sa-cloudscheduler.iam.gserviceaccount.com"

RUNTIME_SA_EMAIL="${RUNTIME_SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
SCHEDULER_SA_EMAIL="${SCHEDULER_SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

if [ -z "$GH_PAT" ] && command -v gh >/dev/null 2>&1; then
  GH_PAT="$(gh auth token 2>/dev/null || true)"
fi

ensure_service_account() {
  local name="$1"
  local display_name="$2"
  local email="${name}@${PROJECT_ID}.iam.gserviceaccount.com"

  if ! gcloud iam service-accounts describe "$email" --project "$PROJECT_ID" >/dev/null 2>&1; then
    gcloud iam service-accounts create "$name" \
      --project "$PROJECT_ID" \
      --display-name "$display_name"
  fi
}

grant_dataset_role() {
  local dataset_ref="${PROJECT_ID}:${DATASET}"
  local member="serviceAccount:${RUNTIME_SA_EMAIL}"
  local role="WRITER"
  local tmp_file
  tmp_file="$(mktemp)"

  bq show --format=prettyjson "$dataset_ref" > "$tmp_file"
  if ! jq -e --arg member "$member" --arg role "$role" '.access[]? | select(.role == $role and .userByEmail == ($member | sub("^serviceAccount:"; "")))' "$tmp_file" >/dev/null; then
    jq --arg member "$member" --arg role "$role" '
      .access += [{"role": $role, "userByEmail": ($member | sub("^serviceAccount:"; ""))}]
    ' "$tmp_file" > "${tmp_file}.new"
    mv "${tmp_file}.new" "$tmp_file"
    bq update --source "$tmp_file" "$dataset_ref" >/dev/null
  fi
  rm -f "$tmp_file"
}

gcloud services enable \
  run.googleapis.com \
  cloudscheduler.googleapis.com \
  secretmanager.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  bigquery.googleapis.com \
  --project "$PROJECT_ID"

if ! bq --location="$REGION" show --dataset "${PROJECT_ID}:${DATASET}" >/dev/null 2>&1; then
  bq --location="$REGION" mk --dataset --description "Daily GitHub access governance snapshots" "${PROJECT_ID}:${DATASET}"
fi

ensure_service_account "$RUNTIME_SA_NAME" "GitHub Access Sync Runtime"
ensure_service_account "$SCHEDULER_SA_NAME" "GitHub Access Sync Scheduler"

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${RUNTIME_SA_EMAIL}" \
  --role="roles/bigquery.jobUser" \
  --condition=None \
  --quiet >/dev/null

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${RUNTIME_SA_EMAIL}" \
  --role="roles/logging.logWriter" \
  --condition=None \
  --quiet >/dev/null

gcloud secrets describe "$SECRET_NAME" --project "$PROJECT_ID" >/dev/null 2>&1 || \
  gcloud secrets create "$SECRET_NAME" --project "$PROJECT_ID" --replication-policy="automatic"

if [ -n "$GH_PAT" ]; then
  printf '%s' "$GH_PAT" | gcloud secrets versions add "$SECRET_NAME" \
    --project "$PROJECT_ID" \
    --data-file=-
fi

if ! gcloud secrets versions list "$SECRET_NAME" --project "$PROJECT_ID" --limit=1 --format='value(name)' | grep -q .; then
  echo "Secret ${SECRET_NAME} has no versions. Set GH_PAT or ensure gh auth token is available, then rerun bootstrap." >&2
  exit 1
fi

gcloud secrets add-iam-policy-binding "$SECRET_NAME" \
  --project "$PROJECT_ID" \
  --member="serviceAccount:${RUNTIME_SA_EMAIL}" \
  --role="roles/secretmanager.secretAccessor" \
  --condition=None \
  --quiet >/dev/null

gcloud iam service-accounts add-iam-policy-binding "$SCHEDULER_SA_EMAIL" \
  --project "$PROJECT_ID" \
  --member="serviceAccount:${SCHEDULER_SERVICE_AGENT}" \
  --role="roles/iam.serviceAccountTokenCreator" \
  --condition=None \
  --quiet >/dev/null

grant_dataset_role

echo "Bootstrap complete for project ${PROJECT_ID}"
echo "Runtime service account: ${RUNTIME_SA_EMAIL}"
echo "Scheduler service account: ${SCHEDULER_SA_EMAIL}"
