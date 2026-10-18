"""Runtime settings from the environment. No model names, project ids or thresholds in code."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv

Mode = Literal["mock", "gcp"]

DEFAULT_CASES_TOPIC = "cases"
DEFAULT_LOCAL_PROJECT = "trustshield-local"


def repo_root() -> Path:
    # trustshield_gateway/settings.py -> services/gateway -> services -> <repo root>
    return Path(__file__).resolve().parents[3]


# Repo-root .env (copied from .env.example). Real environment variables win over the file.
load_dotenv(repo_root() / ".env", override=False)


def mode() -> Mode:
    value = os.environ.get("TRUSTSHIELD_MODE", "mock").strip().lower()
    if value not in ("mock", "gcp"):
        raise ValueError(f"TRUSTSHIELD_MODE must be 'mock' or 'gcp', got {value!r}")
    return value  # type: ignore[return-value]


def require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} must be set when TRUSTSHIELD_MODE=gcp (see .env.example)")
    return value


def firestore_emulator_host() -> str:
    return os.environ.get("FIRESTORE_EMULATOR_HOST", "").strip()


def doc_store_backend() -> str:
    """``firestore`` or ``memory``.

    gcp mode always uses Firestore. In mock mode it uses the local Firestore emulator when
    ``FIRESTORE_EMULATOR_HOST`` is set, and an in-process store otherwise, so tests and a quick
    local run need neither Java nor the Firebase CLI. ``TRUSTSHIELD_DOC_STORE`` overrides.
    """
    override = os.environ.get("TRUSTSHIELD_DOC_STORE", "").strip().lower()
    if override:
        return override
    if mode() == "gcp":
        return "firestore"
    return "firestore" if firestore_emulator_host() else "memory"


def publisher_backend() -> str:
    """``pubsub`` in gcp mode, otherwise a no-op publisher that records what it was given."""
    override = os.environ.get("TRUSTSHIELD_PUBLISHER", "").strip().lower()
    if override:
        return override
    return "pubsub" if mode() == "gcp" else "noop"


def translator_backend() -> str:
    """``google`` (Cloud Translation) in gcp mode, otherwise ``mock`` (text comes back unchanged).
    ``TRUSTSHIELD_TRANSLATOR`` overrides, e.g. ``google`` for a local run with ADC."""
    override = os.environ.get("TRUSTSHIELD_TRANSLATOR", "").strip().lower()
    if override:
        return override
    return "google" if mode() == "gcp" else "mock"


def translation_project_id() -> str:
    """The project billed for Cloud Translation (GCP_PROJECT_ID, needed even in mock mode)."""
    return require_env("GCP_PROJECT_ID") if translator_backend() == "google" else ""


def project_id() -> str:
    """Real project id in gcp mode; any non-empty string satisfies the Firestore emulator."""
    if mode() == "gcp":
        return require_env("GCP_PROJECT_ID")
    return os.environ.get("GCP_PROJECT_ID", "").strip() or DEFAULT_LOCAL_PROJECT


def cases_topic() -> str:
    return os.environ.get("PUBSUB_CASES_TOPIC", DEFAULT_CASES_TOPIC).strip() or DEFAULT_CASES_TOPIC


def cors_allow_origins() -> list[str]:
    """Allowed browser origins, separated by a comma or a semicolon.

    Both work on purpose. A local ``.env`` reads naturally with commas, while the Cloud Run
    deploy has to use semicolons: ``gcloud run deploy --set-env-vars`` already separates its own
    entries with commas, so a comma inside this value would be read as the start of another
    variable. See the CORS section of infra/README.md.
    """
    raw = os.environ.get("CORS_ALLOW_ORIGINS", "http://localhost:5173")
    return [origin.strip() for origin in re.split(r"[,;]", raw) if origin.strip()]
