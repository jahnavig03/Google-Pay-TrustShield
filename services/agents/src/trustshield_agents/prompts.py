"""Load versioned prompt templates from prompts/<name>.<version>.md."""

from __future__ import annotations

from functools import lru_cache

import yaml

from .paths import config_dir, prompts_dir


@lru_cache(maxsize=16)
def load_prompt(name: str, version: str | None = None) -> str:
    if version is None:
        versions = yaml.safe_load((config_dir() / "prompts.yaml").read_text(encoding="utf-8"))
        version = versions[name]
    return (prompts_dir() / f"{name}.{version}.md").read_text(encoding="utf-8")
