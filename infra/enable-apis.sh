#!/usr/bin/env bash
# Enable every Google Cloud API TrustShield uses. Idempotent: an API that is already enabled is
# left alone. Run before bootstrap.sh.
#
#   bash infra/enable-apis.sh [--dry-run] [--project ID] [--region REGION]

source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

usage() { echo "usage: bash infra/enable-apis.sh [--dry-run] [--project ID] [--region REGION]"; }

SERVICES=(
  aiplatform.googleapis.com          # Gemini on Vertex AI
  bigquery.googleapis.com            # feature views + BQML
  pubsub.googleapis.com              # payments / alerts / cases / reports
  run.googleapis.com                 # the gateway
  firestore.googleapis.com           # audit_log, cases, approvals
  documentai.googleapis.com          # screenshot OCR (PayGuard)
  discoveryengine.googleapis.com     # Vertex AI Search over the policy docs
  cloudbuild.googleapis.com          # CI + deploy
  artifactregistry.googleapis.com    # container images
  storage.googleapis.com             # uploads / policies / datasets buckets
  secretmanager.googleapis.com
  logging.googleapis.com
  monitoring.googleapis.com
  firebase.googleapis.com
  firebasehosting.googleapis.com     # web/
  identitytoolkit.googleapis.com
)

main() {
  parse_common_args "$@"
  init

  local enabled missing=()
  enabled="$(gcloud services list --enabled --project "$GCP_PROJECT_ID" \
               --format='value(config.name)' 2>/dev/null || true)"

  for service in "${SERVICES[@]}"; do
    if grep -qx "$service" <<<"$enabled"; then
      exists "$service"
    else
      creating "$service"
      missing+=("$service")
    fi
  done

  if (( ${#missing[@]} == 0 )); then
    done_msg "All ${#SERVICES[@]} APIs are already enabled."
    return 0
  fi

  echo
  run gcloud services enable "${missing[@]}" --project "$GCP_PROJECT_ID"
  if (( DRY_RUN )); then
    done_msg "Dry run: ${#missing[@]} API(s) would be enabled, nothing was changed."
  else
    done_msg "Enabled ${#missing[@]} API(s). Enabling can take a minute to propagate."
  fi
}

main "$@"
