"""Load risk weights / thresholds from config/risk.yaml with per-org overrides."""

from __future__ import annotations

import copy
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, model_validator

from ..paths import config_dir

FEATURE_KEYS = ("A", "B", "D", "L", "V", "S", "N")


class Thresholds(BaseModel):
    warn: float
    step_up: float
    hold: float

    @model_validator(mode="after")
    def _ordered(self) -> Thresholds:
        if not 0 < self.warn < self.step_up < self.hold <= 1:
            raise ValueError("thresholds must satisfy 0 < warn < step_up < hold <= 1")
        return self


class SignalConfig(BaseModel):
    min: int = 3
    max: int = 5
    min_contribution: float = 0.3


class FeatureConfig(BaseModel):
    default_median_amount: float
    amount_ratio_cap: float
    beneficiary_age_tau_minutes: float
    beneficiary_flag_weights: dict[str, float]
    velocity_ratio_cap: float
    mule_link_scale: float
    mule_fan_in_floor: float
    mule_fan_in_span: float


class RiskConfig(BaseModel):
    bias: float
    weights: dict[str, float]
    thresholds: Thresholds
    case_threshold: float
    signals: SignalConfig
    features: FeatureConfig

    @model_validator(mode="after")
    def _all_weights(self) -> RiskConfig:
        missing = set(FEATURE_KEYS) - set(self.weights)
        if missing:
            raise ValueError(f"missing weights: {sorted(missing)}")
        return self


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def _config_path() -> Path:
    return Path(os.environ.get("TRUSTSHIELD_RISK_CONFIG") or config_dir() / "risk.yaml")


@lru_cache(maxsize=32)
def _load(path: Path, org_id: str | None) -> RiskConfig:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    merged = raw["default"]
    if org_id and org_id != "default":
        orgs = raw.get("orgs") or {}
        if org_id not in orgs:
            raise KeyError(f"unknown org_id {org_id!r} in {path}")
        merged = _deep_merge(merged, orgs[org_id])
    return RiskConfig.model_validate(merged)


def load_risk_config(org_id: str | None = None, path: Path | None = None) -> RiskConfig:
    """Config for ``org_id`` (defaults to TRUSTSHIELD_ORG_ID, then the default profile)."""
    org = org_id or os.environ.get("TRUSTSHIELD_ORG_ID") or None
    return _load(path or _config_path(), org)
