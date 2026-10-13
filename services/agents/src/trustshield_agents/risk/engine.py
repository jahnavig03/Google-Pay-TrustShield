"""Risk fusion: R = sigmoid(bias + Σ w_i·x_i), decision bands and top signals."""

from __future__ import annotations

import math

from pydantic import BaseModel
from trustshield_contracts import Decision, Signal

from .config import FEATURE_KEYS, RiskConfig, Thresholds, load_risk_config
from .explain import CODES, explain
from .features import RiskInputs, normalise


class RiskResult(BaseModel):
    risk_score: float
    decision: Decision
    analyst_case_required: bool
    logit: float
    features: dict[str, float]
    contributions: dict[str, float]
    top_signals: list[Signal]


def sigmoid(z: float) -> float:
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-z))
    e = math.exp(z)
    return e / (1.0 + e)


def decide(r: float, t: Thresholds) -> Decision:
    """Bands are lower-bound inclusive: [0, warn) ALLOW, [warn, step_up) WARN, ..."""
    if r >= t.hold:
        return Decision.HOLD_AND_ESCALATE
    if r >= t.step_up:
        return Decision.STEP_UP_VERIFICATION
    if r >= t.warn:
        return Decision.WARN
    return Decision.ALLOW


def needs_case(r: float, cfg: RiskConfig) -> bool:
    return r >= cfg.case_threshold


def score(inputs: RiskInputs, cfg: RiskConfig | None = None) -> RiskResult:
    cfg = cfg or load_risk_config()
    x = normalise(inputs, cfg.features)
    contrib = {k: cfg.weights[k] * x[k] for k in FEATURE_KEYS}
    logit = cfg.bias + sum(contrib.values())
    r = round(sigmoid(logit), 4)

    median = inputs.payer_median_amount or cfg.features.default_median_amount
    ranked = sorted(FEATURE_KEYS, key=lambda k: contrib[k], reverse=True)
    fired = [k for k in ranked if contrib[k] >= cfg.signals.min_contribution]
    chosen = fired[: cfg.signals.max]
    for k in ranked:  # pad to the minimum with the next-highest (reassuring) signals
        if len(chosen) >= cfg.signals.min:
            break
        if k not in chosen:
            chosen.append(k)

    signals = []
    for k in chosen:
        label, text = explain(k, x[k], k in fired, inputs, median)
        signals.append(
            Signal(
                code=CODES[k],
                label=label,
                plain_explanation=text,
                contribution=round(contrib[k], 2),
            )
        )

    return RiskResult(
        risk_score=r,
        decision=decide(r, cfg.thresholds),
        analyst_case_required=needs_case(r, cfg),
        logit=round(logit, 4),
        features={k: round(v, 4) for k, v in x.items()},
        contributions={k: round(v, 4) for k, v in contrib.items()},
        top_signals=signals,
    )
