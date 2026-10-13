"""The four governance rules from CLAUDE.md, one section each."""

from __future__ import annotations

import pytest
from trustshield_contracts import (
    AnalystAction,
    Decision,
    GovernanceOutcome,
    PaymentRiskResponse,
)
from trustshield_contracts.fixtures import load_fixture

from conftest import analyst, customer, merchant
from trustshield_gateway import governance
from trustshield_gateway.audit import AUDIT_COLLECTION

DEMO1 = load_fixture("demo1_payment_85k")


def _response(**overrides) -> PaymentRiskResponse:
    data = {**DEMO1["expected_response"], "audit_id": None, "case_id": None, **overrides}
    return PaymentRiskResponse.model_validate(data)


async def _audit_rows(app) -> list[dict]:
    return await app.state.services.store.list(AUDIT_COLLECTION)


# --------------------------------------------------------------------------------------
# Rule 1 - hold, restrict and escalate require a human approval record
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize("action", ["hold", "restrict", "escalate", "approve_escalation"])
def test_rule1_gated_action_without_approval_record_is_refused(action):
    with pytest.raises(governance.ApprovalRequired):
        governance.require_approval(action, None)


@pytest.mark.parametrize("action", ["hold", "restrict", "escalate", "approve_escalation"])
def test_rule1_gated_action_with_approval_record_is_allowed(action):
    governance.require_approval(action, "APPR-0001")


def test_rule1_ungated_action_needs_no_approval_record():
    governance.require_approval("customer_outreach", None)
    governance.require_approval("close", None)


def test_rule1_hold_decision_is_recorded_as_needs_approval():
    verdict = governance.review(
        evidence_ids=["policy_escalation_04"],
        customer_message="We've paused this payment so you can check it first.",
        decision=Decision.HOLD_AND_ESCALATE,
    )
    assert verdict.outcome is GovernanceOutcome.NEEDS_APPROVAL


def test_rule1_allow_decision_is_permitted():
    verdict = governance.review(
        evidence_ids=["policy_payment_safety_01"],
        customer_message="This payment looks normal.",
        decision=Decision.ALLOW,
    )
    assert verdict.outcome is GovernanceOutcome.PERMITTED


async def test_rule1_decision_route_returns_409_when_the_approval_record_is_missing(
    client, memory_app, monkeypatch
):
    case_id = await _open_demo_case(client)

    # Simulate the approval write not landing: governance must refuse to move the case.
    async def approval_vanishes(collection, doc_id):
        return None

    store = memory_app.state.services.store
    monkeypatch.setattr(store, "get", _only_for("approvals", store.get, approval_vanishes))

    resp = await client.post(
        f"/api/v1/cases/{case_id}/decision",
        headers=analyst(),
        json={
            "action": AnalystAction.APPROVE_ESCALATION.value,
            "analyst_id": "analyst_demo_01",
            "reason": "Escalating the ₹85,000 KYC-urgency payment.",
        },
    )
    assert resp.status_code == 409
    assert "approval" in resp.json()["detail"].lower()

    rows = await _audit_rows(memory_app)
    refused = [row for row in rows if row["governance_outcome"] == "needs_approval"]
    assert refused, "the refused escalation must still be audited"


def _only_for(collection_name, original, replacement):
    async def dispatch(collection, doc_id):
        if collection == collection_name:
            return await replacement(collection, doc_id)
        return await original(collection, doc_id)

    return dispatch


async def _open_demo_case(client) -> str:
    resp = await client.post(
        "/api/v1/payment-risk/evaluate", headers=customer(), json=DEMO1["request"]
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["case_id"]


# --------------------------------------------------------------------------------------
# Rule 2 - no evidence_ids means the action is blocked
# --------------------------------------------------------------------------------------


def test_rule2_empty_evidence_is_blocked():
    with pytest.raises(governance.GovernanceBlocked) as raised:
        governance.check_evidence([])
    assert raised.value.code == governance.BLOCK_NO_EVIDENCE


def test_rule2_non_empty_evidence_passes():
    governance.check_evidence(["policy_kyc_03"])


async def test_rule2_route_returns_422_and_audits_the_block(client, memory_app, monkeypatch):
    _patch_agent_response(monkeypatch, _response(evidence_ids=[]))

    resp = await client.post(
        "/api/v1/payment-risk/evaluate", headers=customer(), json=DEMO1["request"]
    )
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert detail["code"] == governance.BLOCK_NO_EVIDENCE
    assert detail["governance_outcome"] == GovernanceOutcome.BLOCKED.value

    rows = await _audit_rows(memory_app)
    assert len(rows) == 1
    assert rows[0]["governance_outcome"] == "blocked"
    assert rows[0]["audit_id"] == detail["audit_id"]


async def test_rule2_blocked_payment_opens_no_case(client, memory_app, monkeypatch):
    _patch_agent_response(monkeypatch, _response(evidence_ids=[]))
    await client.post("/api/v1/payment-risk/evaluate", headers=customer(), json=DEMO1["request"])
    assert await memory_app.state.services.store.list("cases") == []


# --------------------------------------------------------------------------------------
# Rule 3 - a customer message naming a PIN / OTP / password / CVV / card number is blocked
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "message",
    [
        "Share the OTP sent to your phone to confirm.",
        "Please enter your UPI PIN to continue.",
        "Confirm your password before we release this payment.",
        "Give the agent the CVV printed on the back of your card.",
        "We need your full card number to verify this.",
        "An agent will call you for the one-time password.",
    ],
)
def test_rule3_credential_requests_are_blocked(message):
    with pytest.raises(governance.GovernanceBlocked) as raised:
        governance.check_customer_text(message)
    assert raised.value.code == governance.BLOCK_SENSITIVE_CREDENTIALS


def test_rule3_safe_message_passes():
    governance.check_customer_text(DEMO1["expected_response"]["customer_message"])


async def test_rule3_route_returns_422_audits_and_never_returns_the_message(
    client, memory_app, monkeypatch
):
    unsafe = "Please share the OTP we just sent so we can release this payment."
    _patch_agent_response(monkeypatch, _response(customer_message=unsafe))

    resp = await client.post(
        "/api/v1/payment-risk/evaluate", headers=customer(), json=DEMO1["request"]
    )
    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == governance.BLOCK_SENSITIVE_CREDENTIALS
    # Blocked, not cleaned up: neither the original message nor an edited version comes back.
    assert unsafe not in resp.text
    assert "customer_message" not in resp.json()

    rows = await _audit_rows(memory_app)
    assert [row["governance_outcome"] for row in rows] == ["blocked"]


# --------------------------------------------------------------------------------------
# Rule 4 - every decision gets an audit_id and an audit_log row
# --------------------------------------------------------------------------------------


async def test_rule4_payment_decision_is_audited(client, memory_app):
    resp = await client.post(
        "/api/v1/payment-risk/evaluate", headers=customer(), json=DEMO1["request"]
    )
    body = resp.json()
    rows = await _audit_rows(memory_app)
    assert [row["audit_id"] for row in rows] == [body["audit_id"]]
    row = rows[0]
    assert row["action"] == "payment_risk_decision"
    assert row["subject_id"] == DEMO1["request"]["transaction_id"]
    assert row["evidence_ids"] == body["evidence_ids"]
    assert row["governance_outcome"] == "needs_approval"  # hold recommended, not executed


async def test_rule4_merchant_verification_is_audited(client, memory_app):
    resp = await client.post(
        "/api/v1/merchant/payment-verify",
        headers=merchant(),
        json=load_fixture("demo3_fake_screenshot_12k")["request"],
    )
    assert resp.status_code == 200
    rows = await _audit_rows(memory_app)
    assert rows[0]["audit_id"] == resp.json()["audit_id"]
    assert rows[0]["action"] == "merchant_verify"


async def test_rule4_analyst_decision_is_audited(client, memory_app):
    case_id = await _open_demo_case(client)
    resp = await client.post(
        f"/api/v1/cases/{case_id}/decision",
        headers=analyst(),
        json={
            "action": AnalystAction.APPROVE_ESCALATION.value,
            "analyst_id": "analyst_demo_01",
            "reason": "Account-block urgency message and a brand-new payee.",
        },
    )
    assert resp.status_code == 200
    audit_id = resp.json()["decision"]["audit_id"]
    rows = {row["audit_id"]: row for row in await _audit_rows(memory_app)}
    assert audit_id in rows
    row = rows[audit_id]
    assert row["actor_type"] == "analyst"
    assert row["approval_record_id"], "the audit row must point at the approval record"
    assert row["governance_outcome"] == "permitted"


def _patch_agent_response(monkeypatch, response: PaymentRiskResponse) -> None:
    """Replace the agents call so governance can be driven with a crafted decision."""

    async def fake_evaluate(req):
        return response.model_copy(deep=True)

    monkeypatch.setattr("trustshield_gateway.routes.payment.evaluate_payment_async", fake_evaluate)
