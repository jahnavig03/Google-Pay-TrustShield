"""Where config/, prompts/ and data/ live (services/agents by default)."""

from __future__ import annotations

import os
from pathlib import Path


def agents_home() -> Path:
    override = os.environ.get("TRUSTSHIELD_AGENTS_HOME")
    if override:
        return Path(override)
    # src/trustshield_agents/paths.py -> services/agents
    return Path(__file__).resolve().parents[2]


def config_dir() -> Path:
    return agents_home() / "config"


def prompts_dir() -> Path:
    return agents_home() / "prompts"


def mock_data_dir() -> Path:
    return agents_home() / "data" / "mock"
