"""The ₹85,000 demo-1 fixture, end to end through the gateway."""

from __future__ import annotations

from trustshield_contracts.fixtures import load_fixture

from conftest import customer, requires_firestore_emulator
from trustshield_gateway.audit import AUDIT_COLLECTION
from trustshield_gateway.cases_service import CASES_COLLECTION
from trustshield_gateway.settings import cases_topic

DEMO1 = load_fixture("demo1_payment_85k")
REQUEST = DEMO1["request"]
EXPECTED = DEMO1["expected_response"]


async def test_85k_fixture_returns_hold_and_escalate(client):
    resp = await client.post("/api/v1/payment-risk/evaluate", headers=customer(), json=REQUEST)
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["decision"] == "HOLD_AND_ESCALATE"
    assert body["analyst_case_required"] is True
    assert body["audit_id"]
    assert body["case_id"] == f"CASE-{REQUEST['transaction_id']}"
    assert body["risk_score"] == EXPECTED["risk_score"]
    assert body["evidence_ids"] == EXPECTED["evidence_ids"]
    assert body["top_signals"], "Governance needs top_signals from the agents"


async def test_85k_fixture_writes_an_audit_row(client, memory_app):
    resp = await client.post("/api/v1/payment-risk/evaluate", headers=customer(), json=REQUEST)
    body = resp.json()

    rows = await memory_app.state.services.store.list(AUDIT_COLLECTION)
    assert len(rows) == 1
    row = rows[0]
    assert row["audit_id"] == body["audit_id"]
    assert row["action"] == "payment_risk_decision"
    assert row["subject_type"] == "payment"
    assert row["subject_id"] == REQUEST["transaction_id"]
    assert row["decision"] == "HOLD_AND_ESCALATE"
    assert row["risk_score"] == EXPECTED["risk_score"]
    assert row["evidence_ids"] == EXPECTED["evidence_ids"]


async def test_85k_fixture_opens_a_pending_case_and_publishes_it(client, memory_app):
    resp = await client.post("/api/v1/payment-risk/evaluate", headers=customer(), json=REQUEST)
    case_id = resp.json()["case_id"]

    stored = await memory_app.state.services.store.get(CASES_COLLECTION, case_id)
    assert stored is not None
    assert stored["status"] == "pending_approval"
    assert stored["transaction_id"] == REQUEST["transaction_id"]
    assert stored["amount"] == REQUEST["amount"]
    assert stored["payee_vpa"] == REQUEST["payee_vpa"]
    assert stored["recommended_action"] == "approve_escalation"

    published = memory_app.state.services.publisher.published
    assert published == [(cases_topic(), {"case_id": case_id})]


async def test_hold_is_a_recommendation_not_an_error(client):
    """HOLD_AND_ESCALATE comes back as 200 with a paused-payment message, never a 409."""
    resp = await client.post("/api/v1/payment-risk/evaluate", headers=customer(), json=REQUEST)
    assert resp.status_code == 200
    message = resp.json()["customer_message"]
    assert message and "paused" in message.lower()
    assert resp.json()["safe_actions"], "the customer must be given a safe next action"


async def test_low_risk_payment_opens_no_case(client, memory_app):
    quiet = {
        "transaction_id": "TXN-TEST-SMALL",
        "amount": 250,
        "currency": "INR",
        "payer_id": "payer_demo_001",
        "payee_vpa": "friend.regular@synthbank",
        "beneficiary_age_minutes": 90000,
        "device_changed": False,
        "location_changed": False,
        "message_context": None,
    }
    resp = await client.post("/api/v1/payment-risk/evaluate", headers=customer(), json=quiet)
    assert resp.status_code == 200
    body = resp.json()
    assert body["analyst_case_required"] is False
    assert body["case_id"] is None
    assert body["audit_id"]
    assert await memory_app.state.services.store.list(CASES_COLLECTION) == []


async def test_invalid_payment_request_is_rejected(client):
    bad = {**REQUEST, "amount": 0}
    resp = await client.post("/api/v1/payment-risk/evaluate", headers=customer(), json=bad)
    assert resp.status_code == 422


@requires_firestore_emulator
async def test_85k_fixture_writes_to_the_firestore_emulator(emulator_app):
    """Same flow against `firebase emulators:start --only firestore`."""
    import httpx

    transport = httpx.ASGITransport(app=emulator_app)
    async with (
        emulator_app.router.lifespan_context(emulator_app),
        httpx.AsyncClient(transport=transport, base_url="http://gateway") as http,
    ):
        resp = await http.post("/api/v1/payment-risk/evaluate", headers=customer(), json=REQUEST)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["decision"] == "HOLD_AND_ESCALATE"
        assert body["analyst_case_required"] is True
        assert body["audit_id"] and body["case_id"]

        store = emulator_app.state.services.store
        audit_row = await store.get(AUDIT_COLLECTION, body["audit_id"])
        assert audit_row is not None
        assert audit_row["subject_id"] == REQUEST["transaction_id"]
        case_doc = await store.get(CASES_COLLECTION, body["case_id"])
        assert case_doc is not None and case_doc["status"] == "pending_approval"
