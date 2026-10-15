"""QR checks: unit level and through evaluate_payment (mock mode)."""

import pytest
from trustshield_contracts import Decision, PaymentRiskRequest, QrPayload

from trustshield_agents import evaluate_payment_async
from trustshield_agents.guardrails import customer_text_violations
from trustshield_agents.ports import ScamAssessment, ScamPattern
from trustshield_agents.qr import assess_qr, merge_qr, names_match

TEA_STALL_QR = "upi://pay?pa={pa}&pn=Ramesh%20Tea%20Stall&cu=INR&mc=5812"


def qr(raw: str, name: str | None = "Ramesh Tea Stall", mc: str | None = "5812") -> QrPayload:
    return QrPayload(raw=raw, payee_name=name, merchant_code=mc)


# ---- unit ----


@pytest.mark.parametrize(
    ("a", "b", "match"),
    [
        ("Ramesh Tea Stall", "Ramesh Tea Stall", True),
        ("RAMESH TEA STALL", "Ramesh Tea Stall Pvt", True),
        ("Ramesh Tea Stall", "Sunil Yadav", False),
        ("The Shop", "Store", False),  # only stopwords: never a match
    ],
)
def test_names_match(a, b, match):
    assert names_match(a, b) is match


def test_no_qr_means_no_assessment():
    assert assess_qr(None, "x", False) is None


def test_genuine_shop_qr_has_no_findings():
    a = assess_qr(qr(TEA_STALL_QR.format(pa="chai.ramesh@synthbank")), "Ramesh Tea Stall", True)
    assert a.cues == [] and a.probability == 0


def test_swapped_sticker_is_flagged():
    a = assess_qr(qr(TEA_STALL_QR.format(pa="refund.desk.help@synthbank")), "Sunil Yadav", False)
    assert a.cues == ["qr_name_mismatch", "qr_merchant_unverified"]
    assert a.probability > 0.9


def test_link_qr_is_not_a_payment():
    a = assess_qr(qr("https://kyc-update.example/verify", name=None, mc=None), None, False)
    assert a.cues == ["qr_not_upi_payment"]


def test_merge_keeps_stronger_message_pattern():
    scam = ScamAssessment(
        scam_probability=0.97,
        pattern=ScamPattern.URGENCY,
        manipulation_cues=["account_block"],
        safe_next_step="Pause.",
    )
    merged = merge_qr(scam, assess_qr(qr("upi://pay?pa=x@y", mc=None), "Someone Else", False))
    assert merged.pattern is ScamPattern.URGENCY
    assert merged.manipulation_cues[0] == "qr_name_mismatch"
    assert merged.scam_probability >= 0.97


# ---- end to end (mock mode) ----


def payment(pa: str, qr_payload: QrPayload | None, **extra) -> PaymentRiskRequest:
    return PaymentRiskRequest(
        transaction_id="TXN-QR-TEST",
        amount=extra.pop("amount", 40),
        payer_id="payer_demo_003",
        payee_vpa=pa,
        beneficiary_age_minutes=extra.pop("age", 0),
        qr=qr_payload,
        **extra,
    )


async def test_swapped_sticker_qr_holds_with_a_plain_qr_signal():
    pa = "refund.desk.help@synthbank"
    resp = await evaluate_payment_async(payment(pa, qr(TEA_STALL_QR.format(pa=pa)), amount=2000))
    assert resp.decision is Decision.HOLD_AND_ESCALATE
    assert resp.risk_type == "qr_swap"
    assert "policy_qr_08" in resp.evidence_ids
    signal = next(s for s in resp.top_signals if s.code == "scam_context")
    assert signal.label == "QR name doesn't match"
    assert customer_text_violations(signal.plain_explanation) == []


async def test_genuine_tea_stall_qr_is_allowed_and_reassures():
    pa = "chai.ramesh@synthbank"
    resp = await evaluate_payment_async(payment(pa, qr(TEA_STALL_QR.format(pa=pa))))
    assert resp.decision is Decision.ALLOW
    assert any(s.label == "QR code checked" for s in resp.top_signals)


async def test_same_payment_without_qr_is_unchanged():
    resp = await evaluate_payment_async(payment("chai.ramesh@synthbank", None))
    assert resp.decision is Decision.ALLOW
    assert all(s.label != "QR code checked" for s in resp.top_signals)
