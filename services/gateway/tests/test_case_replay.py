"""Regressions for the two bugs Jahnavi raised after PR #1.

1. Re-evaluating a transaction reset its case, dropping the analyst's decision.
2. ``DocumentStore.create()`` overwrote, so ``audit_log`` was not append-only (rule 4).
"""

from __future__ import annotations

import pytest
from trustshield_contracts.fixtures import load_fixture

from conftest import analyst, customer
from trustshield_gateway.adapters.memory_store import MemoryDocumentStore
from trustshield_gateway.audit import AUDIT_COLLECTION
from trustshield_gateway.cases_service import APPROVALS_COLLECTION, CASES_COLLECTION
from trustshield_gateway.ids import new_approval_id, new_audit_id
from trustshield_gateway.ports import AlreadyExists

DEMO1 = load_fixture("demo1_payment_85k")
REQUEST = DEMO1["request"]
CASE_ID = f"CASE-{REQUEST['transaction_id']}"

APPROVE = {
    "action": "approve_escalation",
    "analyst_id": "analyst_demo_01",
    "reason": "Account-block urgency SMS and a brand-new payee.",
}


async def evaluate(client) -> dict:
    resp = await client.post("/api/v1/payment-risk/evaluate", headers=customer(), json=REQUEST)
    assert resp.status_code == 200, resp.text
    return resp.json()


async def get_case(client) -> dict:
    resp = await client.get(f"/api/v1/cases/{CASE_ID}", headers=analyst())
    assert resp.status_code == 200, resp.text
    return resp.json()


# --------------------------------------------------------------------------------------
# Bug 1 - re-evaluating a transaction must not reset its case
# --------------------------------------------------------------------------------------


async def test_reevaluating_keeps_analyst_decision(client, memory_app):
    """The exact repro from the review: evaluate, approve, evaluate again."""
    first = await evaluate(client)

    decided = await client.post(
        f"/api/v1/cases/{CASE_ID}/decision", headers=analyst(), json=APPROVE
    )
    assert decided.status_code == 200, decided.text

    second = await evaluate(client)

    case = await get_case(client)
    assert case["status"] == "escalated"
    assert case["analyst_decision"] is not None
    assert case["analyst_decision"]["analyst_id"] == "analyst_demo_01"
    assert case["analyst_decision"]["action"] == "approve_escalation"

    risk_events = [e for e in case["timeline"] if e["event_type"] == "risk_decision"]
    assert len(risk_events) == 2, "the original decision and the re-evaluation"
    assert "Re-evaluated:" in risk_events[-1]["description"]
    assert second["audit_id"] in risk_events[-1]["description"]
    assert risk_events[-1]["evidence_id"] == second["evidence_ids"][0]

    assert first["case_id"] == second["case_id"] == CASE_ID

    rows = await memory_app.state.services.store.list(AUDIT_COLLECTION)
    payment_rows = [r for r in rows if r["action"] == "payment_risk_decision"]
    assert len(payment_rows) == 2
    assert {r["audit_id"] for r in payment_rows} == {first["audit_id"], second["audit_id"]}


async def test_case_published_once(client, memory_app):
    await evaluate(client)
    await evaluate(client)

    published = memory_app.state.services.publisher.published
    assert len(published) == 1, "the cases topic must hear about a case exactly once"
    assert published[0][1] == {"case_id": CASE_ID}


async def test_reevaluating_reuses_the_single_case(client, memory_app):
    await evaluate(client)
    await evaluate(client)
    assert len(await memory_app.state.services.store.list(CASES_COLLECTION)) == 1


async def test_reevaluating_keeps_summary_and_approval_record(client, memory_app):
    await evaluate(client)
    summary_before = (await get_case(client))["summary"]
    await client.post(f"/api/v1/cases/{CASE_ID}/decision", headers=analyst(), json=APPROVE)

    await evaluate(client)

    assert (await get_case(client))["summary"] == summary_before
    approvals = await memory_app.state.services.store.list(APPROVALS_COLLECTION)
    assert len(approvals) == 1 and approvals[0]["case_id"] == CASE_ID


# --------------------------------------------------------------------------------------
# Bug 2 - create() is append-only
# --------------------------------------------------------------------------------------


async def test_memory_store_create_rejects_duplicate():
    store = MemoryDocumentStore()
    await store.create(AUDIT_COLLECTION, "AUD-1", {"audit_id": "AUD-1", "decision": "ALLOW"})

    with pytest.raises(AlreadyExists):
        await store.create(AUDIT_COLLECTION, "AUD-1", {"audit_id": "AUD-1", "decision": "HOLD"})

    assert (await store.get(AUDIT_COLLECTION, "AUD-1"))["decision"] == "ALLOW"


def test_audit_and_approval_ids_are_always_fresh():
    """write_audit() and record_approval() mint a new id per call, so they never collide."""
    audit_ids = {new_audit_id() for _ in range(500)}
    approval_ids = {new_approval_id() for _ in range(500)}
    assert len(audit_ids) == 500
    assert len(approval_ids) == 500
    assert all(i.startswith("AUD-") for i in audit_ids)
    assert all(i.startswith("APPR-") for i in approval_ids)


async def test_every_audit_row_is_kept(client, memory_app):
    """Five decisions leave five rows: nothing is silently replaced."""
    for n in range(5):
        resp = await client.post(
            "/api/v1/payment-risk/evaluate",
            headers=customer(),
            json={**REQUEST, "transaction_id": f"TXN-UNIQ-{n}"},
        )
        assert resp.status_code == 200

    rows = await memory_app.state.services.store.list(AUDIT_COLLECTION)
    ids = [r["audit_id"] for r in rows]
    assert len(ids) == len(set(ids)) == 5
