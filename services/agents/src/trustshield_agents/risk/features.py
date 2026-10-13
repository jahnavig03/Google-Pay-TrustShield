"""Raw feature inputs and their 0–1 normalisation functions.

Each function documents its own shape; tuning constants come from config (FeatureConfig).
"""

from __future__ import annotations

import math

from pydantic import BaseModel, Field

from .config import FeatureConfig


class RiskInputs(BaseModel):
    """Everything the engine needs for one payment, before normalisation."""

    amount: float
    payer_median_amount: float | None = None
    beneficiary_age_minutes: int
    beneficiary_flags: list[str] = Field(default_factory=list)
    device_changed: bool = False
    location_changed: bool = False
    txn_count_24h: int = 0
    payer_avg_daily_txn: float = 1.0
    scam_probability: float = 0.0
    scam_pattern: str = "none"
    scam_cues: list[str] = Field(default_factory=list)
    has_message: bool = False
    payee_reported_links: int = 0
    payee_fan_in_24h: int = 0
    payee_is_merchant: bool = False


def _clamp(x: float) -> float:
    return max(0.0, min(1.0, x))


def _noisy_or(*probs: float) -> float:
    """P(at least one) for independent risks: 1 - Π(1 - p)."""
    out = 1.0
    for p in probs:
        out *= 1.0 - _clamp(p)
    return 1.0 - out


def amount_deviation(amount: float, median: float, cfg: FeatureConfig) -> float:
    """A: log-scaled ratio to the payer's median. ≤ 1x → 0, `amount_ratio_cap`x → 1.

    Log scale because payment sizes are multiplicative: 2x is mildly unusual, 50x is extreme.
    """
    ratio = amount / max(median, 1.0)
    if ratio <= 1.0:
        return 0.0
    return _clamp(math.log(ratio) / math.log(cfg.amount_ratio_cap))


def beneficiary_risk(age_minutes: int, flags: list[str], cfg: FeatureConfig) -> float:
    """B: exponential decay on payee age, noisy-OR'd with weighted payee flags.

    exp(-age/tau): added just now → 1, after `beneficiary_age_tau_minutes` → 0.37, weeks → 0.
    Unknown flags are ignored.
    """
    age_risk = math.exp(-max(age_minutes, 0) / cfg.beneficiary_age_tau_minutes)
    flag_risks = [cfg.beneficiary_flag_weights.get(f, 0.0) for f in flags]
    return _noisy_or(age_risk, *flag_risks)


def device_anomaly(device_changed: bool) -> float:
    """D: 1 if the payment comes from a device not previously bound to the payer, else 0."""
    return 1.0 if device_changed else 0.0


def location_anomaly(location_changed: bool) -> float:
    """L: 1 if the payment location is outside the payer's usual locations, else 0."""
    return 1.0 if location_changed else 0.0


def velocity(txn_count_24h: int, avg_daily_txn: float, cfg: FeatureConfig) -> float:
    """V: (24h count incl. this payment) / usual daily count. 1x → 0, `velocity_ratio_cap`x → 1."""
    ratio = (txn_count_24h + 1) / max(avg_daily_txn, 1.0)
    return _clamp((ratio - 1.0) / (cfg.velocity_ratio_cap - 1.0))


def scam_context(probability: float) -> float:
    """S: the Scam Context agent's probability, clamped to [0, 1]."""
    return _clamp(probability)


def mule_network(
    reported_links: int, fan_in_24h: int, is_merchant: bool, cfg: FeatureConfig
) -> float:
    """N: noisy-OR of (a) links to reported accounts, 1 - exp(-links/scale), and
    (b) fan-in: many distinct payers paying this payee in 24h, linear above `mule_fan_in_floor`.
    Fan-in is ignored for registered merchants, who are paid by many people by design."""
    link_risk = 1.0 - math.exp(-max(reported_links, 0) / cfg.mule_link_scale)
    fan_in_risk = 0.0
    if not is_merchant:
        fan_in_risk = _clamp((fan_in_24h - cfg.mule_fan_in_floor) / cfg.mule_fan_in_span)
    return _noisy_or(link_risk, fan_in_risk)


def normalise(inputs: RiskInputs, cfg: FeatureConfig) -> dict[str, float]:
    median = inputs.payer_median_amount or cfg.default_median_amount
    return {
        "A": amount_deviation(inputs.amount, median, cfg),
        "B": beneficiary_risk(inputs.beneficiary_age_minutes, inputs.beneficiary_flags, cfg),
        "D": device_anomaly(inputs.device_changed),
        "L": location_anomaly(inputs.location_changed),
        "V": velocity(inputs.txn_count_24h, inputs.payer_avg_daily_txn, cfg),
        "S": scam_context(inputs.scam_probability),
        "N": mule_network(
            inputs.payee_reported_links, inputs.payee_fan_in_24h, inputs.payee_is_merchant, cfg
        ),
    }
