"""The contract must stay compatible with the gateway's original request/response."""

from trustshield_contracts import Decision, PaymentRiskRequest, PaymentRiskResponse
from trustshield_contracts.api import ENDPOINTS

# Shape of the gateway's original fake response (before the agents were wired in).
GATEWAY_FAKE_RESPONSE = {
    "risk_score": 0.42,
    "decision": "WARN",
    "risk_type": "behavioural_anomaly",
    "customer_message": "Please double-check this recipient before paying.",
    "analyst_case_required": False,
    "evidence_ids": ["policy_payment_safety_02"],
}


def test_gateway_request_minimal_fields_validate():
    req = PaymentRiskRequest(
        transaction_id="t1",
        amount=500,
        payer_id="p1",
        payee_vpa="a@synthbank",
        beneficiary_age_minutes=100000,
    )
    assert req.currency == "INR"
    assert req.device_changed is False and req.location_changed is False
    assert req.message_context is None and req.attachment_uri is None


def test_gateway_fake_response_still_validates():
    resp = PaymentRiskResponse.model_validate(GATEWAY_FAKE_RESPONSE)
    assert resp.decision is Decision.WARN
    assert resp.top_signals == [] and resp.audit_id is None
    # Original keys keep their names and JSON types.
    dumped = resp.model_dump(mode="json")
    for key, value in GATEWAY_FAKE_RESPONSE.items():
        assert dumped[key] == value


def test_decision_enum_values():
    assert [d.value for d in Decision] == [
        "ALLOW",
        "WARN",
        "STEP_UP_VERIFICATION",
        "HOLD_AND_ESCALATE",
    ]


def test_endpoint_paths():
    assert {(e.method, e.path) for e in ENDPOINTS} == {
        ("POST", "/api/v1/payment-risk/evaluate"),
        ("POST", "/api/v1/merchant/payment-verify"),
        ("GET", "/api/v1/cases"),
        ("GET", "/api/v1/cases/{case_id}"),
        ("POST", "/api/v1/cases/{case_id}/ask"),
        ("POST", "/api/v1/cases/{case_id}/decision"),
    }


def test_qr_field_is_optional_and_validated():
    from trustshield_contracts import QrPayload

    base = {
        "transaction_id": "t1",
        "amount": 40,
        "payer_id": "p1",
        "payee_vpa": "a@synthbank",
        "beneficiary_age_minutes": 10,
    }
    assert PaymentRiskRequest(**base).qr is None
    req = PaymentRiskRequest(
        **base,
        qr={
            "raw": "upi://pay?pa=a@synthbank&pn=A&cu=INR",
            "payee_name": "A",
            "merchant_code": "5812",
        },
    )
    assert isinstance(req.qr, QrPayload) and req.qr.payee_name == "A"
