"""Analyst case routes: list, get, ask, decision."""

from __future__ import annotations

import pytest
from trustshield_contracts import NOT_COVERED_BY_POLICY
from trustshield_contracts.fixtures import load_fixture

from conftest import analyst, customer
from trustshield_gateway.cases_service import APPROVALS_COLLECTION

DEMO1 = load_fixture("demo1_payment_85k")
DEMO2 = load_fixture("demo2_analyst_case")


async def open_case(client) -> str:
    resp = await client.post(
        "/api/v1/payment-risk/evaluate", headers=customer(), json=DEMO1["request"]
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["case_id"]


async def test_case_list_is_empty_before_any_payment(client):
    resp = await client.get("/api/v1/cases", headers=analyst())
    assert resp.status_code == 200
    assert resp.json() == {"cases": []}


async def test_case_appears_in_the_list_after_the_85k_payment(client):
    case_id = await open_case(client)
    resp = await client.get("/api/v1/cases", headers=analyst())
    cases = resp.json()["cases"]
    assert len(cases) == 1
    row = cases[0]
    assert row["case_id"] == case_id
    assert row["status"] == "pending_approval"
    assert row["decision"] == "HOLD_AND_ESCALATE"
    assert row["amount"] == DEMO1["request"]["amount"]
    assert row["payee_vpa"] == DEMO1["request"]["payee_vpa"]


async def test_get_case_returns_the_timeline_and_signals(client):
    case_id = await open_case(client)
    resp = await client.get(f"/api/v1/cases/{case_id}", headers=analyst())
    assert resp.status_code == 200
    case = resp.json()
    assert case["case_id"] == case_id
    assert case["status"] == "pending_approval"
    assert case["top_signals"]
    assert {event["event_type"] for event in case["timeline"]} >= {
        "payment_initiated",
        "risk_decision",
        "case_created",
    }
    assert case["evidence_ids"] == DEMO1["expected_response"]["evidence_ids"]
    assert case["analyst_decision"] is None


async def test_get_unknown_case_is_404(client):
    resp = await client.get("/api/v1/cases/CASE-does-not-exist", headers=analyst())
    assert resp.status_code == 404


async def test_new_case_carries_the_cited_policy_passages(client):
    case_id = await open_case(client)
    case = (await client.get(f"/api/v1/cases/{case_id}", headers=analyst())).json()
    cited = [c["evidence_id"] for c in case["citations"]]
    assert cited == case["evidence_ids"]
    assert all(c["title"] and c["snippet"] for c in case["citations"])
    assert case["missing_evidence"] == []


async def test_ask_why_answers_from_the_signals_and_cites_policy(client):
    case_id = await open_case(client)
    resp = await client.post(
        f"/api/v1/cases/{case_id}/ask",
        headers=analyst(),
        json=DEMO2["ask_request"],
    )
    assert resp.status_code == 200
    body = resp.json()
    cited = [c["evidence_id"] for c in body["citations"]]
    assert cited == ["policy_payment_safety_01", "policy_kyc_03"]
    for evidence_id in cited:
        assert f"[{evidence_id}]" in body["answer"]
    assert "Urgent message" in body["answer"]


async def test_ask_with_nothing_retrieved_is_exactly_not_covered_by_policy(client):
    case_id = await open_case(client)
    resp = await client.post(
        f"/api/v1/cases/{case_id}/ask",
        headers=analyst(),
        json={"question": "Who won the cricket match?"},
    )
    assert resp.status_code == 200
    assert resp.json() == {"answer": NOT_COVERED_BY_POLICY, "citations": []}


async def test_ask_on_an_unknown_case_is_404(client):
    resp = await client.post(
        "/api/v1/cases/CASE-nope/ask", headers=analyst(), json={"question": "Why?"}
    )
    assert resp.status_code == 404


@pytest.mark.parametrize(
    ("action", "expected_status"),
    [
        ("approve_escalation", "escalated"),
        ("customer_outreach", "customer_outreach"),
        ("close", "closed"),
    ],
)
async def test_decision_moves_the_case(client, action, expected_status):
    case_id = await open_case(client)
    resp = await client.post(
        f"/api/v1/cases/{case_id}/decision",
        headers=analyst(),
        json={"action": action, "analyst_id": "analyst_demo_01", "reason": "Reviewed the case."},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["case_id"] == case_id
    assert body["status"] == expected_status
    assert body["decision"]["action"] == action
    assert body["decision"]["audit_id"]

    stored = await client.get(f"/api/v1/cases/{case_id}", headers=analyst())
    assert stored.json()["status"] == expected_status
    assert stored.json()["analyst_decision"]["analyst_id"] == "analyst_demo_01"


async def test_decision_writes_an_approval_record(client, memory_app):
    case_id = await open_case(client)
    await client.post(
        f"/api/v1/cases/{case_id}/decision",
        headers=analyst(),
        json=DEMO2["decision_request"],
    )
    approvals = await memory_app.state.services.store.list(APPROVALS_COLLECTION)
    assert len(approvals) == 1
    approval = approvals[0]
    assert approval["case_id"] == case_id
    assert approval["action"] == "approve_escalation"
    assert approval["analyst_id"] == DEMO2["decision_request"]["analyst_id"]


async def test_decision_on_an_unknown_case_is_404(client):
    resp = await client.post(
        "/api/v1/cases/CASE-nope/decision",
        headers=analyst(),
        json={"action": "close", "analyst_id": "a1", "reason": "n/a"},
    )
    assert resp.status_code == 404


async def test_decision_needs_a_reason(client):
    case_id = await open_case(client)
    resp = await client.post(
        f"/api/v1/cases/{case_id}/decision",
        headers=analyst(),
        json={"action": "close", "analyst_id": "a1", "reason": ""},
    )
    assert resp.status_code == 422
