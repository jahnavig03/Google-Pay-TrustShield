"""Fusion step: specialist outputs + risk engine -> PaymentRiskResponse (no ADK, easy to test)."""

from __future__ import annotations

from trustshield_contracts import (
    Decision,
    PaymentRiskRequest,
    PaymentRiskResponse,
    RiskType,
    SafeAction,
    SafeActionCode,
)

from .adapters.factory import Services
from .ports import MessageInputs, PayeeFeatures, PayerFeatures, ScamAssessment, ScamPattern
from .risk import RiskConfig, RiskInputs, RiskResult, load_risk_config, score

_ACTIONS = {
    SafeActionCode.PROCEED: "Continue with the payment",
    SafeActionCode.VERIFY_RECIPIENT: "Check the recipient's details with them directly",
    SafeActionCode.CANCEL_PAYMENT: "Cancel this payment",
    SafeActionCode.CONTACT_BANK_OFFICIAL: "Call your bank using the number on its official app or card",
    SafeActionCode.REPORT_SCAM: "Report this request",
}
_ACTIONS_BY_DECISION = {
    Decision.ALLOW: [SafeActionCode.PROCEED],
    Decision.WARN: [SafeActionCode.VERIFY_RECIPIENT, SafeActionCode.CANCEL_PAYMENT],
    Decision.STEP_UP_VERIFICATION: [SafeActionCode.VERIFY_RECIPIENT, SafeActionCode.CANCEL_PAYMENT],
    Decision.HOLD_AND_ESCALATE: [
        SafeActionCode.CANCEL_PAYMENT,
        SafeActionCode.CONTACT_BANK_OFFICIAL,
    ],
}


def build_risk_inputs(
    req: PaymentRiskRequest, payer: PayerFeatures, payee: PayeeFeatures, scam: ScamAssessment
) -> RiskInputs:
    return RiskInputs(
        amount=req.amount,
        payer_median_amount=payer.median_amount,
        beneficiary_age_minutes=req.beneficiary_age_minutes,
        beneficiary_flags=payee.flags,
        device_changed=req.device_changed,
        location_changed=req.location_changed,
        txn_count_24h=payer.txn_count_24h,
        payer_avg_daily_txn=payer.avg_daily_txn,
        scam_probability=scam.scam_probability,
        scam_pattern=scam.pattern.value,
        scam_cues=scam.manipulation_cues,
        has_message=bool((req.message_context or "").strip()),
        payee_reported_links=payee.reported_links,
        payee_fan_in_24h=payee.fan_in_24h,
        payee_is_merchant=payee.is_merchant,
    )


def risk_type_for(result: RiskResult, scam: ScamAssessment, cfg: RiskConfig) -> str:
    fired = cfg.signals.min_contribution
    if result.contributions["S"] >= fired and scam.pattern is not ScamPattern.NONE:
        return scam.pattern.value
    if result.decision is Decision.ALLOW:
        return RiskType.NONE.value
    if result.contributions["N"] >= fired:
        return RiskType.MULE_NETWORK.value
    return RiskType.BEHAVIOURAL_ANOMALY.value


def safe_actions_for(decision: Decision) -> list[SafeAction]:
    return [SafeAction(code=c, label=_ACTIONS[c]) for c in _ACTIONS_BY_DECISION[decision]]


async def fuse(
    req: PaymentRiskRequest,
    payer: PayerFeatures,
    payee: PayeeFeatures,
    scam: ScamAssessment,
    services: Services,
    cfg: RiskConfig | None = None,
) -> PaymentRiskResponse:
    cfg = cfg or load_risk_config()
    result = score(build_risk_inputs(req, payer, payee, scam), cfg)
    risk_type = risk_type_for(result, scam, cfg)
    safe_actions = safe_actions_for(result.decision)
    evidence_ids = services.evidence.evidence_ids(risk_type, result.decision)
    message = await services.messages.write(
        MessageInputs(
            decision=result.decision,
            risk_type=risk_type,
            signals=result.top_signals,
            safe_actions=safe_actions,
            safe_next_step=scam.safe_next_step,
            citations=services.evidence.citations(evidence_ids),
        )
    )
    return PaymentRiskResponse(
        risk_score=result.risk_score,
        decision=result.decision,
        risk_type=risk_type,
        customer_message=message,
        analyst_case_required=result.analyst_case_required,
        evidence_ids=evidence_ids,
        top_signals=result.top_signals,
        safe_actions=safe_actions,
        case_id=None,  # cases are opened by the gateway / PayInvestigator
        audit_id=None,  # filled in by gateway Governance
    )
