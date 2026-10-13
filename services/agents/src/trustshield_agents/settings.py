"""Runtime settings from the environment. Nothing here hard-codes models, projects or thresholds."""

from __future__ import annotations

import os
from typing import Literal

from dotenv import load_dotenv

from .paths import agents_home

Mode = Literal["mock", "gcp"]

# Repo-root .env (copied from .env.example). Real environment variables win over the file.
load_dotenv(agents_home().parents[1] / ".env", override=False)


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


def feature_store_backend() -> str:
    """json (default, both modes) or bigquery (once Ronak's feature views exist)."""
    return os.environ.get("TRUSTSHIELD_FEATURE_STORE", "json").strip().lower()
