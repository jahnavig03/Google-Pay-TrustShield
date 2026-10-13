"""Prompt 4: evaluate_payment through the ADK workflow in mock mode."""

import asyncio

from trustshield_contracts import Decision, PaymentRiskRequest, PaymentRiskResponse

from trustshield_agents import evaluate_payment, evaluate_payment_async
from trustshield_agents.guardrails import customer_text_violations


async def test_demo1_full_path(demo1_request):
    resp = await evaluate_payment_async(demo1_request)
    assert isinstance(resp, PaymentRiskResponse)
    assert resp.decision is Decision.HOLD_AND_ESCALATE
    assert resp.analyst_case_required
    assert resp.risk_type == "urgency"
    assert resp.top_signals and resp.evidence_ids  # Governance needs both
    assert "policy_escalation_04" in resp.evidence_ids
    assert resp.audit_id is None and resp.case_id is None  # gateway owns these
    assert 1 <= len(resp.safe_actions) <= 2
    assert customer_text_violations(resp.customer_message) == []


async def test_allow_path_still_has_signals_and_evidence():
    resp = await evaluate_payment_async(
        PaymentRiskRequest(
            transaction_id="t-allow",
            amount=500,
            payer_id="payer_demo_003",
            payee_vpa="chai.ramesh@synthbank",
            beneficiary_age_minutes=500000,
        )
    )
    assert resp.decision is Decision.ALLOW
    assert len(resp.top_signals) >= 3 and resp.evidence_ids
    assert resp.safe_actions[0].code == "proceed"


def test_sync_wrapper_outside_loop(demo1_request):
    assert evaluate_payment(demo1_request).decision is Decision.HOLD_AND_ESCALATE


async def test_sync_wrapper_inside_running_loop(demo1_request):
    # e.g. called from a FastAPI async handler
    assert evaluate_payment(demo1_request).decision is Decision.HOLD_AND_ESCALATE


async def test_concurrent_calls_are_isolated(demo1_request):
    small = demo1_request.model_copy(
        update={
            "transaction_id": "t2",
            "amount": 100,
            "message_context": None,
            "device_changed": False,
            "payee_vpa": "landlord.sharma@synthbank",
            "beneficiary_age_minutes": 10**6,
        }
    )
    a, b = await asyncio.gather(
        evaluate_payment_async(demo1_request), evaluate_payment_async(small)
    )
    assert a.decision is Decision.HOLD_AND_ESCALATE and b.decision is Decision.ALLOW


async def test_mock_latency_budget(demo1_request):
    import time

    await evaluate_payment_async(demo1_request)
    t0 = time.perf_counter()
    for _ in range(5):
        await evaluate_payment_async(demo1_request)
    assert (time.perf_counter() - t0) / 5 < 0.8  # PRD p50 SLO is 800 ms
