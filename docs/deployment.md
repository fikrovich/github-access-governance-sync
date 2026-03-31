# Deployment Guide

This guide describes the intended GCP deployment model for the public version of the project.

## Deployment Target

The reference deployment uses:

- Cloud Run for execution
- Cloud Scheduler for daily triggering
- Secret Manager for GitHub token storage
- BigQuery for storage and reporting

## Required Environment Variables

The deployment scripts support the following variables:

| Variable | Required | Description | Example |
|---|---|---|---|
| `PROJECT_ID` | yes | GCP project ID | `example-gcp-project` |
| `REGION` | yes | Cloud Run, Scheduler, and BigQuery location | `us-central1` |
| `DATASET` | yes | BigQuery dataset name | `github_access_audit` |
| `ORG` | yes | GitHub organization to export | `example-org` |
| `SERVICE_NAME` | no | Cloud Run service name | `github-access-sync` |
| `SECRET_NAME` | no | Secret Manager secret holding the GitHub token | `github-access-token` |
| `RUNTIME_SA_NAME` | no | Cloud Run runtime service account name | `github-access-sync-sa` |
| `SCHEDULER_SA_NAME` | no | Cloud Scheduler caller service account name | `github-access-sync-scheduler` |
| `SCHEDULER_JOB_NAME` | no | Scheduler job name | `github-access-sync-daily` |
| `SCHEDULER_TIMEZONE` | no | Scheduler timezone | `Etc/UTC` |
| `SCHEDULER_SCHEDULE` | no | Scheduler cron | `0 8 * * *` |
| `GH_PAT` | conditionally | GitHub PAT to seed Secret Manager | `github_pat_xxx` |

## IAM Model

### Runtime Service Account

The Cloud Run runtime service account needs:

- `roles/bigquery.jobUser` on the project
- dataset write access on the target dataset
- `roles/logging.logWriter` on the project
- `roles/secretmanager.secretAccessor` on the GitHub token secret

### Scheduler Caller Service Account

The Cloud Scheduler caller service account needs:

- `roles/run.invoker` on the Cloud Run service

### Cloud Scheduler Service Agent

The Cloud Scheduler service agent needs:

- `roles/iam.serviceAccountTokenCreator` on the scheduler caller service account

This is required so Scheduler can mint the OIDC token used to call the private Cloud Run service.

## Deployment Sequence

### 1. Authenticate GCP

```bash
gcloud auth login
gcloud config set project "${PROJECT_ID}"
```

### 2. Set Variables

```bash
export PROJECT_ID='example-gcp-project'
export REGION='us-central1'
export DATASET='github_access_audit'
export ORG='example-org'
export SERVICE_NAME='github-access-sync'
export SECRET_NAME='github-access-token'
export GH_PAT='your_pat'
```

### 3. Deploy

```bash
cd <repo-dir>
bash scripts/deploy.sh
```

The deployment flow:

1. enables required GCP services
2. creates the BigQuery dataset if it does not exist
3. creates service accounts if they do not exist
4. creates or updates the GitHub token secret
5. grants required IAM bindings
6. deploys the Cloud Run service from source
7. creates or updates the Cloud Scheduler job

## Manual Validation

After deployment, validate the service and job configuration.

### Check Cloud Run

```bash
gcloud run services describe "${SERVICE_NAME}" \
  --project "${PROJECT_ID}" \
  --region "${REGION}"
```

### Trigger A Manual Sync

```bash
SERVICE_URL="$(gcloud run services describe "${SERVICE_NAME}" \
  --project "${PROJECT_ID}" \
  --region "${REGION}" \
  --format='value(status.url)')"

curl -X POST "${SERVICE_URL}/sync"
```

For a private service, use an authenticated call path rather than an anonymous request.

### Check Scheduler

```bash
gcloud scheduler jobs describe "${SCHEDULER_JOB_NAME}" \
  --project "${PROJECT_ID}" \
  --location "${REGION}"
```

### Check BigQuery Outputs

```bash
bq ls "${PROJECT_ID}:${DATASET}"
bq query --use_legacy_sql=false "SELECT * FROM \`${PROJECT_ID}.${DATASET}.sync_runs\` ORDER BY started_at DESC LIMIT 5"
```

## Operational Recommendations

- keep the service private
- use a dedicated GitHub token for this workload
- review `sync_skipped_items` after failures or unusual volume changes
- monitor `sync_runs.status`, `loaded_rows`, and `skipped_items`
- start with a test organization or non-sensitive dataset before production rollout

## Common Failure Modes

### Invalid GitHub Token

Symptoms:

- exporter fails during token validation
- no CSV outputs are produced

Action:

- rotate the token
- update the secret
- rerun the sync

### BigQuery Permission Failure

Symptoms:

- load job errors
- view refresh errors

Action:

- verify runtime service account IAM
- verify dataset-level access entries

### Scheduler Invocation Failure

Symptoms:

- job exists but sync never starts
- HTTP auth errors in Scheduler execution logs

Action:

- verify `roles/run.invoker` on the Cloud Run service
- verify the scheduler service agent has token-creator access on the caller service account

### GitHub API Throttling Or Availability Issues

Symptoms:

- many skipped items
- partial loads

Action:

- inspect `sync_skipped_items`
- verify token scope and rate limits
- reduce concurrency only if you later redesign the exporter
