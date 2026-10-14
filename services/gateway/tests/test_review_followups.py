"""Regressions for the follow-ups from the PR #2 review.

1. Concurrent re-evaluations of one transaction lost timeline events (read-modify-write).
2. A higher-risk re-evaluation left the case showing the original, lower score and decision.
3. The first payment after start-up paid ~2-3 s of agent set-up; the gateway now warms up.
"""

from __future__ import annotations

import asyncio
import time

import pytest
from trustshield_contracts.fixtures import load_fixture

from conftest import analyst, customer, requires_firestore_emulator
from trustshield_gateway.adapters.memory_store import MemoryDocumentStore

DEMO1 = load_fixture("demo1_payment_85k")["request"]


def requests_for(txn: str) -> tuple[dict, dict]:
    """Same transaction scored twice: first at STEP_UP, then (with the scam SMS and a new
    device) at HOLD_AND_ESCALATE."""
    step_up = {
        **DEMO1,
        "transaction_id": txn,
        "amount": 20000,
        "message_context": None,
        "device_changed": False,
    }
    hold = {**DEMO1, "transaction_id": txn}
    return step_up, hold


async def evaluate(client, body: dict) -> dict:
    resp = await client.post("/api/v1/payment-risk/evaluate", headers=customer(), json=body)
    assert resp.status_code == 200, resp.text
    return resp.json()


async def get_case(client, case_id: str) -> dict:
    resp = await client.get(f"/api/v1/cases/{case_id}", headers=analyst())
    assert resp.status_code == 200, resp.text
    return resp.json()


def risk_events(case: dict) -> list[dict]:
    return [e for e in case["timeline"] if e["event_type"] == "risk_decision"]


# ---- 1. no lost timeline events ----


async def test_concurrent_replays_keep_every_timeline_event(client):
    """Behaviour check on the in-process store. The in-process store never interleaves, so the
    real race only reproduces against Firestore: see the emulator test at the bottom, which
    loses events on the old read-modify-write code (2 of 6 kept)."""
    body = {**DEMO1, "transaction_id": "TXN-CONCURRENT-1"}
    first = await evaluate(client, body)
    await asyncio.gather(*(evaluate(client, body) for _ in range(5)))

    case = await get_case(client, first["case_id"])
    assert len(risk_events(case)) == 6  # 1 from opening the case + 5 re-evaluations


async def test_memory_store_append_is_atomic_and_needs_the_document():
    store = MemoryDocumentStore()
    await store.create("cases", "C1", {"timeline": []})
    await asyncio.gather(*(store.append("cases", "C1", "timeline", {"n": i}) for i in range(20)))
    assert len((await store.get("cases", "C1"))["timeline"]) == 20
    with pytest.raises(KeyError):
        await store.append("cases", "missing", "timeline", {})


# ---- 2. the case shows the peak risk, never lower ----


async def test_higher_score_replay_raises_case_risk(client):
    step_up, hold = requests_for("TXN-RAISE-1")
    first = await evaluate(client, step_up)
    assert first["decision"] == "STEP_UP_VERIFICATION"
    case = await get_case(client, first["case_id"])
    assert case["recommended_action"] == "customer_outreach"

    second = await evaluate(client, hold)
    assert second["decision"] == "HOLD_AND_ESCALATE"
    assert second["case_id"] == first["case_id"]

    case = await get_case(client, first["case_id"])
    assert case["risk_score"] == second["risk_score"] > first["risk_score"]
    assert case["decision"] == "HOLD_AND_ESCALATE"
    assert case["recommended_action"] == "approve_escalation"
    assert case["status"] == "pending_approval"
    listed = (await client.get("/api/v1/cases", headers=analyst())).json()["cases"]
    assert next(c for c in listed if c["case_id"] == first["case_id"])["decision"] == (
        "HOLD_AND_ESCALATE"
    )


async def test_lower_score_replay_keeps_case_risk(client):
    step_up, hold = requests_for("TXN-LOWER-1")
    first = await evaluate(client, hold)
    await evaluate(client, step_up)

    case = await get_case(client, first["case_id"])
    assert case["risk_score"] == first["risk_score"]
    assert case["decision"] == "HOLD_AND_ESCALATE"
    assert len(risk_events(case)) == 2  # the lower score is still on the timeline


async def test_raising_risk_keeps_the_analyst_decision(client):
    step_up, hold = requests_for("TXN-RAISE-DECIDED")
    first = await evaluate(client, step_up)
    resp = await client.post(
        f"/api/v1/cases/{first['case_id']}/decision",
        headers=analyst(),
        json={"action": "customer_outreach", "analyst_id": "analyst_demo_01", "reason": "Call."},
    )
    assert resp.status_code == 200, resp.text

    await evaluate(client, hold)
    case = await get_case(client, first["case_id"])
    assert case["decision"] == "HOLD_AND_ESCALATE"
    assert case["status"] == "customer_outreach"
    assert case["analyst_decision"]["action"] == "customer_outreach"


async def test_memory_store_update_if_greater():
    store = MemoryDocumentStore()
    await store.create("cases", "C1", {"risk_score": 0.8, "decision": "STEP_UP_VERIFICATION"})
    assert (
        await store.update_if_greater("cases", "C1", "risk_score", 0.7, {"decision": "x"}) is False
    )
    assert (
        await store.update_if_greater("cases", "C1", "risk_score", 0.8, {"decision": "x"}) is False
    )
    assert await store.update_if_greater("cases", "C1", "risk_score", 0.95, {"decision": "HOLD"})
    assert await store.get("cases", "C1") == {"risk_score": 0.95, "decision": "HOLD"}


# ---- 3. warm-up at start-up ----


async def test_gateway_warms_up_agents_at_startup(memory_app, monkeypatch):
    calls: list[float] = []

    async def fake_warm_up() -> None:
        calls.append(time.monotonic())

    monkeypatch.setattr("trustshield_gateway.app.warm_up_async", fake_warm_up)
    async with memory_app.router.lifespan_context(memory_app):
        assert len(calls) == 1


# ---- the same guarantees against the real Firestore emulator ----


@requires_firestore_emulator
async def test_concurrent_replays_and_raise_on_the_emulator(emulator_app):
    import httpx

    txn = f"TXN-EMU-FOLLOWUP-{time.time_ns()}"
    step_up, hold = requests_for(txn)
    transport = httpx.ASGITransport(app=emulator_app)
    async with (
        emulator_app.router.lifespan_context(emulator_app),
        httpx.AsyncClient(transport=transport, base_url="http://gateway") as http,
    ):
        first = await evaluate(http, step_up)
        await asyncio.gather(*(evaluate(http, hold) for _ in range(5)))
        case = await get_case(http, first["case_id"])

    assert len(risk_events(case)) == 6
    assert case["decision"] == "HOLD_AND_ESCALATE"
    assert case["risk_score"] > first["risk_score"]
