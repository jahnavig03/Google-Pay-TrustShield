#!/usr/bin/env bash
# Batch-load data/out/*.parquet into BigQuery and (re)create the two feature views.
#
#   python -m generator --seed 42          # from data/, writes data/out/
#   bash data/bq/load.sh [--dry-run] [--project ID] [--region REGION]
#
# Free tier only (team cost rule):
#   - batch `bq load` from local Parquet (load jobs are free); never streaming inserts
#   - every query is run with --dry_run first and the bytes it would process are printed
#   - --dry-run changes nothing: it prints each command and only runs BigQuery's own (free)
#     --dry_run validation, which needs the tables to exist from an earlier real run
# Safe to re-run: tables are CREATE IF NOT EXISTS, emptied with TRUNCATE (free) and re-loaded;
# views are CREATE OR REPLACE.

source "$(dirname "${BASH_SOURCE[0]}")/../../infra/lib.sh"

usage() { echo "usage: bash data/bq/load.sh [--dry-run] [--project ID] [--region REGION]"; }

BQ_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT_DIR="$(cd "$BQ_DIR/.." && pwd)/out"
# Load order doesn't matter (no foreign keys); meta + demo_* feed the views.
TABLES=(accounts devices transactions beneficiaries labels merchants merchant_ledger
        meta demo_payer_features demo_payee_features)
VIEWS=(v_payer_features v_payee_features)

# BQ_DATASET: environment, then the repo-root .env, then the default.
dataset_from_env_file() {
  local env_file
  env_file="$(repo_root)/.env"
  [[ -f "$env_file" ]] || return 0
  grep -E "^BQ_DATASET=" "$env_file" | tail -n1 | cut -d= -f2- | tr -d '"'"'"' ' || true
}

render() {  # SQL file -> SQL with {{project}} / {{dataset}} filled in
  sed -e "s/{{project}}/${GCP_PROJECT_ID}/g" -e "s/{{dataset}}/${BQ_DATASET}/g" "$1"
}

bq_query() { bq --project_id="$GCP_PROJECT_ID" --location="$GCP_REGION" query --use_legacy_sql=false "$@"; }

# Dry-run a query (always, even in --dry-run mode: it is free and changes nothing) and print
# the bytes it would process. Returns non-zero if BigQuery rejects it.
dry_run() {
  local label="$1" sql="$2" out
  if out="$(bq_query --dry_run <<<"$sql" 2>&1)"; then
    printf '   dry run:   %-34s %s bytes\n' "$label" "$(grep -oE '[0-9]+ bytes' <<<"$out" | grep -oE '[0-9]+' || echo '?')"
    return 0
  fi
  printf '   dry run:   %-34s FAILED: %s\n' "$label" "$(grep -v '^\s*$' <<<"$out" | tail -n1)"
  return 1
}

# Dry-run, then run. In --dry-run mode a failed dry run (e.g. the table doesn't exist yet) is
# reported and skipped; in a real run it stops the script.
sql_step() {
  local label="$1" sql="$2"
  if ! dry_run "$label" "$sql"; then
    (( DRY_RUN )) && return 0
    echo "ERROR: dry run failed for $label; nothing more was run." >&2
    exit 1
  fi
  if (( DRY_RUN )); then
    echo "   would run: bq query ($label)"
  else
    bq_query --quiet <<<"$sql" >/dev/null
    echo "   ran:       $label"
  fi
}

# ---------------------------------------------------------------------------------------------

check_outputs() {
  echo "Generated files (${OUT_DIR})"
  local missing=0 t
  for t in "${TABLES[@]}"; do
    if [[ -f "$OUT_DIR/$t.parquet" ]]; then
      printf '   %-24s %s\n' "$t.parquet" "$(du -h "$OUT_DIR/$t.parquet" | cut -f1)"
    else
      echo "   MISSING $t.parquet"; missing=1
    fi
  done
  if (( missing )); then
    echo "ERROR: run 'cd data && python -m generator --seed 42' first." >&2
    exit 1
  fi
  echo
}

dataset() {
  echo "Dataset ${GCP_PROJECT_ID}:${BQ_DATASET}"
  if bq --project_id="$GCP_PROJECT_ID" show --dataset "${GCP_PROJECT_ID}:${BQ_DATASET}" >/dev/null 2>&1; then
    exists "${GCP_PROJECT_ID}:${BQ_DATASET}"
  else
    creating "${GCP_PROJECT_ID}:${BQ_DATASET}"
    run bq --project_id="$GCP_PROJECT_ID" --location="$GCP_REGION" mk --dataset \
      --description "TrustShield synthetic features and feature views" \
      "${GCP_PROJECT_ID}:${BQ_DATASET}"
  fi
  echo
}

tables() {
  echo "Tables (DDL: data/bq/schema/*.sql)"
  local t
  for t in "${TABLES[@]}"; do
    sql_step "schema/$t.sql" "$(render "$BQ_DIR/schema/$t.sql")"
  done
  echo
}

load() {
  echo "Batch loads (bq load, free; no streaming)"
  local t
  for t in "${TABLES[@]}"; do
    sql_step "truncate $t" "TRUNCATE TABLE \`${GCP_PROJECT_ID}.${BQ_DATASET}.${t}\`"
    # Append into the DDL-created table so its descriptions and clustering are kept.
    run bq --project_id="$GCP_PROJECT_ID" --location="$GCP_REGION" load \
      --source_format=PARQUET \
      --parquet_enable_list_inference=true \
      "${GCP_PROJECT_ID}:${BQ_DATASET}.${t}" \
      "$OUT_DIR/$t.parquet"
  done
  echo
}

views() {
  echo "Feature views (data/bq/views/*.sql)"
  local v
  for v in "${VIEWS[@]}"; do
    sql_step "views/$v.sql" "$(render "$BQ_DIR/views/$v.sql")"
  done
  echo
}

lookup_costs() {
  # What one agents' feature lookup would process (BigQueryFeatureStore runs one per payment).
  echo "Per-lookup cost (dry run only)"
  local p="${GCP_PROJECT_ID}.${BQ_DATASET}"
  dry_run "payer lookup" "SELECT * FROM \`$p.v_payer_features\` WHERE payer_id = 'payer_demo_001'" || true
  dry_run "payee lookup" "SELECT * FROM \`$p.v_payee_features\` WHERE payee_vpa = 'kyc.helpdesk.verify@synthbank'" || true
  echo
}

# ---------------------------------------------------------------------------------------------

parse_common_args "$@"
init
need bq
BQ_DATASET="${BQ_DATASET:-$(dataset_from_env_file)}"
BQ_DATASET="${BQ_DATASET:-trustshield}"
echo "dataset=$BQ_DATASET  out=$OUT_DIR"
echo

check_outputs
dataset
tables
load
views
lookup_costs
if (( DRY_RUN )); then
  done_msg "Dry run only: nothing was created or loaded."
else
  done_msg "Loaded. Check the views match features.json: data/.venv/bin/python data/bq/verify.py"
fi
