"""Case storage and the analyst flow (Firestore ``cases`` and ``approvals`` collections).

Case content beyond what the risk decision already provides (full timeline, linked accounts,
retrieved citations, grounded Q&A) comes from Jahnavi's Investigator agent. Until it lands the
gateway stores what it can see and answers questions with "not covered by policy".
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from trustshield_contracts import (
    NOT_COVERED_BY_POLICY,
    AnalystAction,
    AnalystDecision,
    Case,
    CaseAnswer,
    CaseStatus,
    CaseSummary,
    Decision,
    EntityType,
    LinkedEntity,
    PaymentRiskRequest,
    PaymentRiskResponse,
    TimelineEvent,
)

from .audit import now
from .ids import case_id_for, new_approval_id
from .ports import DocumentStore

CASES_COLLECTION = "cases"
APPROVALS_COLLECTION = "approvals"

#: What each analyst action does to the case status.
STATUS_AFTER_ACTION: dict[AnalystAction, CaseStatus] = {
    AnalystAction.APPROVE_ESCALATION: CaseStatus.ESCALATED,
    AnalystAction.CUSTOMER_OUTREACH: CaseStatus.CUSTOMER_OUTREACH,
    AnalystAction.CLOSE: CaseStatus.CLOSED,
}


def _summary_text(req: PaymentRiskRequest, resp: PaymentRiskResponse) -> str:
    lead = (
        f"{req.currency} {req.amount:,.0f} to {req.payee_vpa} scored R = {resp.risk_score:.4f} "
        f"({resp.decision.value}, risk type {resp.risk_type})."
    )
    signals = "; ".join(signal.plain_explanation for signal in resp.top_signals[:3])
    return f"{lead} Top signals: {signals}" if signals else lead


def _timeline(
    req: PaymentRiskRequest, resp: PaymentRiskResponse, created_at: datetime
) -> list[TimelineEvent]:
    events = [
        TimelineEvent(
            timestamp=created_at,
            event_type="payment_initiated",
            description=(f"{req.currency} {req.amount:,.0f} payment initiated to {req.payee_vpa}."),
        ),
        TimelineEvent(
            timestamp=created_at,
            event_type="risk_decision",
            description=f"R = {resp.risk_score:.4f} -> {resp.decision.value}.",
            evidence_id=resp.evidence_ids[0] if resp.evidence_ids else None,
        ),
        TimelineEvent(
            timestamp=created_at,
            event_type="case_created",
            description="Case auto-created (R >= 0.70) and is waiting for analyst approval.",
        ),
    ]
    if req.message_context:
        events.insert(
            0,
            TimelineEvent(
                timestamp=created_at,
                event_type="message_received",
                description="A message was attached to this payment and assessed for scam context.",
            ),
        )
    return events


def _linked_entities(req: PaymentRiskRequest) -> list[LinkedEntity]:
    entities = [
        LinkedEntity(entity_type=EntityType.ACCOUNT, entity_id=req.payer_id, relation="payer"),
        LinkedEntity(entity_type=EntityType.VPA, entity_id=req.payee_vpa, relation="payee"),
    ]
    if req.device_changed:
        entities.append(
            LinkedEntity(
                entity_type=EntityType.DEVICE,
                entity_id=f"new-device-for-{req.payer_id}",
                relation="payer_new_device",
                risk_note="First seen on this payment.",
            )
        )
    return entities


def build_case(req: PaymentRiskRequest, resp: PaymentRiskResponse) -> Case:
    """The case the gateway opens when ``analyst_case_required`` is true."""
    created_at = now()
    recommended = (
        AnalystAction.APPROVE_ESCALATION
        if resp.decision is Decision.HOLD_AND_ESCALATE
        else AnalystAction.CUSTOMER_OUTREACH
    )
    return Case(
        case_id=case_id_for(req.transaction_id),
        transaction_id=req.transaction_id,
        created_at=created_at,
        status=CaseStatus.PENDING_APPROVAL,
        risk_score=resp.risk_score,
        decision=resp.decision,
        risk_type=resp.risk_type,
        summary=_summary_text(req, resp),
        top_signals=list(resp.top_signals),
        timeline=_timeline(req, resp, created_at),
        linked_entities=_linked_entities(req),
        citations=[],  # Filled by the Investigator's Evidence & Policy agent.
        recommended_action=recommended,
        missing_evidence=["Retrieved policy citations not attached yet (Investigator pending)."],
        evidence_ids=list(resp.evidence_ids),
    )


def _to_document(case: Case, req: PaymentRiskRequest) -> dict[str, Any]:
    """Case plus the two fields the analyst list needs that the Case model does not carry."""
    return {**case.model_dump(mode="json"), "amount": req.amount, "payee_vpa": req.payee_vpa}


async def save_case(store: DocumentStore, case: Case, req: PaymentRiskRequest) -> None:
    await store.create(CASES_COLLECTION, case.case_id, _to_document(case, req))


async def get_case_document(store: DocumentStore, case_id: str) -> dict[str, Any] | None:
    return await store.get(CASES_COLLECTION, case_id)


async def list_case_summaries(store: DocumentStore) -> list[CaseSummary]:
    docs = await store.list(CASES_COLLECTION, order_by="created_at", descending=True)
    return [CaseSummary.model_validate(doc) for doc in docs]


async def record_approval(
    store: DocumentStore,
    *,
    case_id: str,
    action: AnalystAction,
    analyst_id: str,
    reason: str,
    decided_at: datetime,
) -> str:
    """Write the human approval record that governance rule 1 asks for. Returns its id."""
    approval_record_id = new_approval_id()
    await store.create(
        APPROVALS_COLLECTION,
        approval_record_id,
        {
            "approval_record_id": approval_record_id,
            "case_id": case_id,
            "action": action.value,
            "analyst_id": analyst_id,
            "reason": reason,
            "decided_at": decided_at.isoformat(),
        },
    )
    return approval_record_id


async def apply_decision(
    store: DocumentStore, *, case_id: str, decision: AnalystDecision
) -> CaseStatus:
    status = STATUS_AFTER_ACTION[decision.action]
    await store.update(
        CASES_COLLECTION,
        case_id,
        {"status": status.value, "analyst_decision": decision.model_dump(mode="json")},
    )
    return status


async def answer_question(case: Case, question: str) -> CaseAnswer:
    """Grounded Q&A. Nothing is retrieved yet, so the answer is exactly "not covered by policy".

    Replace the body with a call into Jahnavi's Investigator agent; the contract stays the same.
    """
    del case, question
    return CaseAnswer(answer=NOT_COVERED_BY_POLICY, citations=[])
