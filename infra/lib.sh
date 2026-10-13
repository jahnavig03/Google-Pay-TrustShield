#!/usr/bin/env bash
# Shared helpers for the infra scripts. Source it, don't run it.
#
#   GCP_PROJECT_ID / GCP_REGION come from the environment, then the repo-root .env, then the
#   defaults below. Every script takes --dry-run, which prints the commands and changes nothing.

set -euo pipefail

DEFAULT_PROJECT_ID="qualified-sun-511214-t1"
DEFAULT_REGION="asia-south1"

DRY_RUN=0

infra_dir() { cd "$(dirname "${BASH_SOURCE[0]}")" && pwd; }
repo_root() { cd "$(infra_dir)/.." && pwd; }

# Pull GCP_PROJECT_ID / GCP_REGION out of the repo-root .env without executing it.
load_env_file() {
  local env_file="$(repo_root)/.env"
  [[ -f "$env_file" ]] || return 0
  local key value
  for key in GCP_PROJECT_ID GCP_REGION; do
    [[ -n "${!key:-}" ]] && continue
    value="$(grep -E "^${key}=" "$env_file" | tail -n1 | cut -d= -f2- | tr -d '"'"'"' ' || true)"
    [[ -n "$value" ]] && export "$key=$value"
  done
  return 0
}

parse_common_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --dry-run) DRY_RUN=1 ;;
      --project) shift; export GCP_PROJECT_ID="$1" ;;
      --region)  shift; export GCP_REGION="$1" ;;
      -h|--help) usage; exit 0 ;;
      *) echo "unknown argument: $1" >&2; usage; exit 2 ;;
    esac
    shift
  done
}

init() {
  load_env_file
  export GCP_PROJECT_ID="${GCP_PROJECT_ID:-$DEFAULT_PROJECT_ID}"
  export GCP_REGION="${GCP_REGION:-$DEFAULT_REGION}"
  need gcloud
  echo "project=$GCP_PROJECT_ID  region=$GCP_REGION  dry_run=$DRY_RUN"
  echo
}

need() {
  command -v "$1" >/dev/null 2>&1 || { echo "ERROR: '$1' is not on PATH." >&2; exit 1; }
}

# Print the command shell-quoted so a --dry-run line can be copy-pasted as-is.
quoted() { local out="" a; for a in "$@"; do out+="${out:+ }$(printf '%q' "$a")"; done; echo "$out"; }

run() {
  if (( DRY_RUN )); then
    echo "   would run: $(quoted "$@")"
  else
    echo "   running:   $(quoted "$@")"
    "$@"
  fi
}

exists()  { printf '  [exists] %s\n' "$*"; }
creating(){ printf '  [create] %s\n' "$*"; }
done_msg(){ printf '\n%s\n' "$*"; }
