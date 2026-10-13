#!/usr/bin/env bash
# Create every TrustShield resource that does not exist yet. Safe to re-run: each step checks
# first and reports [exists] or [create]. Run enable-apis.sh before this.
#
#   bash infra/bootstrap.sh [--dry-run] [--project ID] [--region REGION]
#
# Creates: three Cloud Storage buckets, Firestore (native), the BigQuery dataset, four Pub/Sub
# topics and the Artifact Registry docker repo.

source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

usage() { echo "usage: bash infra/bootstrap.sh [--dry-run] [--project ID] [--region REGION]"; }

BUCKET_SUFFIXES=(uploads policies datasets)
PUBSUB_TOPICS=(payments alerts cases reports)
BQ_DATASET="${BQ_DATASET:-trustshield}"
ARTIFACT_REPO="${ARTIFACT_REPO:-trustshield}"

# ---------------------------------------------------------------------------------------------

buckets() {
  echo "Cloud Storage buckets"
  local name
  for suffix in "${BUCKET_SUFFIXES[@]}"; do
    name="${GCP_PROJECT_ID}-${suffix}"
    if gcloud storage buckets describe "gs://${name}" --project "$GCP_PROJECT_ID" \
         --format='value(name)' >/dev/null 2>&1; then
      exists "gs://${name}"
    else
      creating "gs://${name}"
      # gcloud storage, not gsutil. Uniform access + public access prevention by default.
      run gcloud storage buckets create "gs://${name}" \
        --project "$GCP_PROJECT_ID" \
        --location "$GCP_REGION" \
        --uniform-bucket-level-access \
        --public-access-prevention
    fi
  done
  echo
}

firestore_database() {
  echo "Firestore (native mode, ${GCP_REGION})"
  if gcloud firestore databases describe --database='(default)' \
       --project "$GCP_PROJECT_ID" --format='value(name)' >/dev/null 2>&1; then
    exists "(default) database"
  else
    creating "(default) database"
    run gcloud firestore databases create \
      --project "$GCP_PROJECT_ID" \
      --location "$GCP_REGION" \
      --type firestore-native
  fi
  echo
}

bigquery_dataset() {
  echo "BigQuery dataset"
  need bq
  if bq --project_id="$GCP_PROJECT_ID" show --dataset "${GCP_PROJECT_ID}:${BQ_DATASET}" \
       >/dev/null 2>&1; then
    exists "${GCP_PROJECT_ID}:${BQ_DATASET}"
  else
    creating "${GCP_PROJECT_ID}:${BQ_DATASET}"
    run bq --project_id="$GCP_PROJECT_ID" --location="$GCP_REGION" mk \
      --dataset \
      --description "TrustShield synthetic features and feature views" \
      "${GCP_PROJECT_ID}:${BQ_DATASET}"
  fi
  echo
}

pubsub_topics() {
  echo "Pub/Sub topics"
  for topic in "${PUBSUB_TOPICS[@]}"; do
    if gcloud pubsub topics describe "$topic" --project "$GCP_PROJECT_ID" \
         --format='value(name)' >/dev/null 2>&1; then
      exists "topic ${topic}"
    else
      creating "topic ${topic}"
      run gcloud pubsub topics create "$topic" --project "$GCP_PROJECT_ID"
    fi
  done
  echo
}

artifact_registry() {
  echo "Artifact Registry"
  if gcloud artifacts repositories describe "$ARTIFACT_REPO" \
       --project "$GCP_PROJECT_ID" --location "$GCP_REGION" \
       --format='value(name)' >/dev/null 2>&1; then
    exists "docker repo ${ARTIFACT_REPO} (${GCP_REGION})"
  else
    creating "docker repo ${ARTIFACT_REPO} (${GCP_REGION})"
    run gcloud artifacts repositories create "$ARTIFACT_REPO" \
      --project "$GCP_PROJECT_ID" \
      --location "$GCP_REGION" \
      --repository-format docker \
      --description "TrustShield service images"
  fi
  echo
}

main() {
  parse_common_args "$@"
  init
  buckets
  firestore_database
  bigquery_dataset
  pubsub_topics
  artifact_registry
  if (( DRY_RUN )); then
    done_msg "Dry run: nothing was changed."
  else
    done_msg "Bootstrap complete."
  fi
}

main "$@"
