"""PayInvestigator: the analyst case routes under /api/v1/cases."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from trustshield_contracts import (
    AnalystDecision,
    AnalystDecisionRequest,
    Case,
    CaseAnswer,
    CaseDecisionResponse,
    CaseListResponse,
    CaseQuestion,
    GovernanceOutcome,
)

from .. import cases_service, governance
from ..audit import now, write_audit
from ..deps import StoreDep
from ..ids import new_audit_id
from ..ports import DocumentStore
from ..security import ANALYST, require_role

router = APIRouter(
    prefix="/api/v1/cases", tags=["investigator"], dependencies=[Depends(require_role(ANALYST))]
)

ACTION = "analyst_decision"


async def _load_case(store: DocumentStore, case_id: str) -> Case:
    document = await cases_service.get_case_document(store, case_id)
    if document is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"Case {case_id} not found.")
    return Case.model_validate(document)


@router.get(
    "", response_model=CaseListResponse, operation_id="listCases", summary="List analyst cases"
)
async def list_cases(store: StoreDep) -> CaseListResponse:
    return CaseListResponse(cases=await cases_service.list_case_summaries(store))


@router.get(
    "/{case_id}",
    response_model=Case,
    operation_id="getCase",
    summary="Get one case with timeline, links and citations",
)
async def get_case(case_id: str, store: StoreDep) -> Case:
    return await _load_case(store, case_id)


@router.post(
    "/{case_id}/ask",
    response_model=CaseAnswer,
    operation_id="askCase",
    summary="Grounded Q&A over a case",
)
async def ask_case(case_id: str, body: CaseQuestion, store: StoreDep) -> CaseAnswer:
    case = await _load_case(store, case_id)
    return await cases_service.answer_question(case, body.question)


@router.post(
    "/{case_id}/decision",
    response_model=CaseDecisionResponse,
    operation_id="decideCase",
    summary="Record the analyst's decision (human approval)",
)
async def decide_case(
    case_id: str, body: AnalystDecisionRequest, store: StoreDep
) -> CaseDecisionResponse:
    """Record the human approval, then apply it. Rule 1 is checked before the case moves."""
    case = await _load_case(store, case_id)
    decided_at = now()

    approval_record_id = await cases_service.record_approval(
        store,
        case_id=case_id,
        action=body.action,
        analyst_id=body.analyst_id,
        reason=body.reason,
        decided_at=decided_at,
    )
    # Read the approval back: rule 1 is about an approval record existing, not about having
    # tried to write one.
    stored = await store.get(cases_service.APPROVALS_COLLECTION, approval_record_id)
    try:
        governance.require_approval(body.action.value, approval_record_id if stored else None)
    except governance.ApprovalRequired as needed:
        await write_audit(
            store,
            actor_type="analyst",
            actor_id=body.analyst_id,
            action=ACTION,
            subject_type="case",
            subject_id=case_id,
            decision=body.action.value,
            risk_score=case.risk_score,
            evidence_ids=case.evidence_ids,
            governance_outcome=GovernanceOutcome.NEEDS_APPROVAL,
            reason=needed.reason,
        )
        raise HTTPException(status.HTTP_409_CONFLICT, detail=needed.reason) from needed

    decision = AnalystDecision(
        action=body.action,
        analyst_id=body.analyst_id,
        reason=body.reason,
        decided_at=decided_at,
        audit_id=new_audit_id(),
    )
    new_status = await cases_service.apply_decision(store, case_id=case_id, decision=decision)

    await write_audit(
        store,
        audit_id=decision.audit_id,
        actor_type="analyst",
        actor_id=body.analyst_id,
        action=ACTION,
        subject_type="case",
        subject_id=case_id,
        decision=body.action.value,
        risk_score=case.risk_score,
        evidence_ids=case.evidence_ids,
        approval_record_id=approval_record_id,
        governance_outcome=GovernanceOutcome.PERMITTED,
        reason=f"Analyst recorded '{body.action.value}'; case is now {new_status.value}.",
    )
    return CaseDecisionResponse(case_id=case_id, status=new_status, decision=decision)
