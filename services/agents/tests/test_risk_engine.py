"""Prompt 3 acceptance tests for the risk-fusion engine."""

import pytest
from trustshield_contracts import Decision

from trustshield_agents.adapters.json_feature_store import JsonFeatureStore
from trustshield_agents.adapters.rule_scam_classifier import RuleScamClassifier
from trustshield_agents.fusion import build_risk_inputs
from trustshield_agents.risk import RiskInputs, decide, load_risk_config, needs_case, score
from trustshield_agents.risk.features import (
    amount_deviation,
    beneficiary_risk,
    mule_network,
    velocity,
)

YEAR_MIN = 60 * 24 * 365


async def _demo1_inputs(req):
    store = JsonFeatureStore()
    scam = RuleScamClassifier().classify_sync(req.message_context)
    return build_risk_inputs(
        req, await store.payer(req.payer_id), await store.payee(req.payee_vpa), scam
    )


# (a) the ₹85,000 scam
async def test_demo1_holds_with_expected_signals(demo1_request, cfg):
    result = score(await _demo1_inputs(demo1_request), cfg)
    assert result.risk_score >= 0.90
    assert result.decision is Decision.HOLD_AND_ESCALATE
    assert result.analyst_case_required
    codes = {s.code for s in result.top_signals}
    assert {"new_beneficiary", "amount_deviation", "device_anomaly", "scam_context"} <= codes
    assert 3 <= len(result.top_signals) <= 5
    contributions = [s.contribution for s in result.top_signals]
    assert contributions == sorted(contributions, reverse=True)
    urgency = next(s for s in result.top_signals if s.code == "scam_context")
    assert "blocked" in urgency.plain_explanation
    new_payee = next(s for s in result.top_signals if s.code == "new_beneficiary")
    assert new_payee.plain_explanation == "The recipient was added 4 minutes ago."


# (b) normal small payment to a long-standing payee
def test_normal_500_to_old_payee_allows(cfg):
    result = score(
        RiskInputs(
            amount=500,
            payer_median_amount=650,
            beneficiary_age_minutes=2 * YEAR_MIN,
            txn_count_24h=2,
            payer_avg_daily_txn=4,
        ),
        cfg,
    )
    assert result.decision is Decision.ALLOW
    assert not result.analyst_case_required
    assert len(result.top_signals) == 3  # padded with reassuring signals


# (c) hard negatives
def test_large_rent_to_old_payee_does_not_hold(cfg):
    result = score(
        RiskInputs(
            amount=25000,
            payer_median_amount=2000,
            beneficiary_age_minutes=400 * 24 * 60,
            has_message=True,
            scam_probability=0.1,
        ),
        cfg,
    )
    assert result.decision not in (Decision.HOLD_AND_ESCALATE, Decision.STEP_UP_VERIFICATION)
    assert result.decision is Decision.ALLOW


def test_new_genuine_payee_small_amount_does_not_hold(cfg):
    result = score(
        RiskInputs(amount=300, payer_median_amount=650, beneficiary_age_minutes=2),
        cfg,
    )
    assert result.decision is not Decision.HOLD_AND_ESCALATE
    assert result.decision is Decision.ALLOW
    assert result.top_signals[0].code == "new_beneficiary"


def test_rent_with_legit_urgent_reminder_does_not_hold(cfg):
    scam = RuleScamClassifier().classify_sync(
        "Hi, gentle reminder that the rent of Rs 25,000 is due today. Thanks!"
    )
    result = score(
        RiskInputs(
            amount=25000,
            payer_median_amount=2000,
            beneficiary_age_minutes=400 * 24 * 60,
            scam_probability=scam.scam_probability,
            scam_pattern=scam.pattern.value,
            has_message=True,
        ),
        cfg,
    )
    assert result.decision is Decision.ALLOW


# (d) exact threshold boundaries
@pytest.mark.parametrize(
    ("r", "expected"),
    [
        (0.0, Decision.ALLOW),
        (0.3499, Decision.ALLOW),
        (0.35, Decision.WARN),
        (0.6999, Decision.WARN),
        (0.70, Decision.STEP_UP_VERIFICATION),
        (0.8999, Decision.STEP_UP_VERIFICATION),
        (0.90, Decision.HOLD_AND_ESCALATE),
        (1.0, Decision.HOLD_AND_ESCALATE),
    ],
)
def test_threshold_boundaries(r, expected, cfg):
    assert decide(r, cfg.thresholds) is expected


@pytest.mark.parametrize(("r", "case"), [(0.6999, False), (0.70, True), (0.95, True)])
def test_case_threshold_boundary(r, case, cfg):
    assert needs_case(r, cfg) is case


def test_org_override_changes_thresholds_only():
    strict = load_risk_config("demo_strict_bank")
    default = load_risk_config()
    assert strict.thresholds.hold == 0.85 and strict.case_threshold == 0.60
    assert strict.weights == default.weights
    assert decide(0.86, strict.thresholds) is Decision.HOLD_AND_ESCALATE
    assert decide(0.86, default.thresholds) is Decision.STEP_UP_VERIFICATION


def test_org_from_env(monkeypatch):
    monkeypatch.setenv("TRUSTSHIELD_ORG_ID", "demo_strict_bank")
    assert load_risk_config().thresholds.warn == 0.30


def test_unknown_org_raises():
    with pytest.raises(KeyError):
        load_risk_config("no_such_org")


# feature normalisation functions stay in [0, 1] and are monotone
def test_feature_functions(cfg):
    f = cfg.features
    assert amount_deviation(500, 1000, f) == 0
    assert amount_deviation(1000 * f.amount_ratio_cap, 1000, f) == pytest.approx(1)
    assert amount_deviation(5000, 1000, f) < amount_deviation(20000, 1000, f) <= 1
    assert beneficiary_risk(0, [], f) == pytest.approx(1)
    assert beneficiary_risk(YEAR_MIN, [], f) == pytest.approx(0, abs=1e-6)
    assert beneficiary_risk(YEAR_MIN, ["reported_by_users"], f) == pytest.approx(0.6)
    assert velocity(1, 2, f) == 0 and velocity(100, 2, f) == 1
    assert mule_network(0, 0, False, f) == 0
    assert mule_network(0, 50, True, f) == 0  # merchants are paid by many people by design
    assert 0 < mule_network(1, 0, False, f) < mule_network(3, 0, False, f) < 1


def test_every_signal_explanation_is_non_accusatory(demo1_request, cfg):
    from trustshield_agents.guardrails import customer_text_violations

    for amount, age, dev in [(85000, 4, True), (200, 10**6, False)]:
        result = score(
            RiskInputs(
                amount=amount,
                payer_median_amount=1800,
                beneficiary_age_minutes=age,
                beneficiary_flags=["reported_by_users"],
                device_changed=dev,
                location_changed=dev,
                txn_count_24h=10,
                scam_probability=0.9,
                scam_pattern="fake_refund",
                payee_reported_links=2,
            ),
            cfg,
        )
        for s in result.top_signals:
            assert customer_text_violations(s.plain_explanation) == [], s
