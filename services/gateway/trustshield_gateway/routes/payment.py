"""PaySafe Interceptor: POST /api/v1/payment-risk/evaluate."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from trustshield_agents import evaluate_payment_async
from trustshield_contracts import GovernanceOutcome, PaymentRiskRequest, PaymentRiskResponse

from .. import cases_service, governance
from ..audit import write_audit
from ..deps import PublisherDep, ServicesDep, StoreDep
from ..governance import HTTP_422_BLOCKED
from ..ids import new_audit_id
from ..ports import AlreadyExists
from ..security import CUSTOMER, require_role
from ..settings import cases_topic

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["paysafe"])

ACTION = "payment_risk_decision"


@router.post(
    "/payment-risk/evaluate",
    response_model=PaymentRiskResponse,
    operation_id="evaluatePaymentRisk",
    summary="Score a payment and return allow / warn / step-up / hold",
    dependencies=[Depends(require_role(CUSTOMER))],
)
async def evaluate_payment_risk(
    req: PaymentRiskRequest,
    services: ServicesDep,
    store: StoreDep,
    publisher: PublisherDep,
) -> PaymentRiskResponse:
    """Score the payment, run Governance over the result, open a case if one is needed.

    ``HOLD_AND_ESCALATE`` comes back as a recommendation to the customer (payment paused, case
    opened), not an error: the hold itself is executed only after an analyst approves it.
    """
    del services
    resp = await evaluate_payment_async(req)

    try:
        verdict = governance.review(
            evidence_ids=resp.evidence_ids,
            customer_message=resp.customer_message,
            decision=resp.decision,
        )
    except governance.GovernanceBlocked as blocked:
        # Rules 2 and 3: block the action and still leave an audit trail (rule 4).
        record = await write_audit(
            store,
            actor_type="system",
            actor_id="gateway",
            action=ACTION,
            subject_type="payment",
            subject_id=req.transaction_id,
            decision=resp.decision.value,
            risk_score=resp.risk_score,
            evidence_ids=resp.evidence_ids,
            governance_outcome=GovernanceOutcome.BLOCKED,
            reason=blocked.reason,
        )
        log.warning("governance blocked %s: %s", req.transaction_id, blocked.code)
        raise HTTPException(
            HTTP_422_BLOCKED,
            detail={
                "governance_outcome": GovernanceOutcome.BLOCKED.value,
                "code": blocked.code,
                "reason": blocked.reason,
                "audit_id": record.audit_id,
            },
        ) from blocked

    # Rule 4 first: the decision is audited before anything acts on it, so a later failure
    # cannot leave a decision with no audit row.
    resp.audit_id = new_audit_id()
    await write_audit(
        store,
        audit_id=resp.audit_id,
        actor_type="system",
        actor_id="gateway",
        action=ACTION,
        subject_type="payment",
        subject_id=req.transaction_id,
        decision=resp.decision.value,
        risk_score=resp.risk_score,
        evidence_ids=resp.evidence_ids,
        governance_outcome=verdict.outcome,
        reason=verdict.reason,
    )

    if resp.analyst_case_required:
        case = cases_service.build_case(req, resp)
        resp.case_id = case.case_id
        existing = await cases_service.get_case_document(store, case.case_id)

        if existing is None:
            try:
                await cases_service.save_case(store, case, req)
            except AlreadyExists:
                # Two evaluations of the same transaction raced; the other one opened the case.
                existing = await cases_service.get_case_document(store, case.case_id)
            else:
                try:
                    await publisher.publish(cases_topic(), {"case_id": case.case_id})
                except Exception:
                    # The case is already in Firestore, which is what the analyst UI reads. A
                    # failed notification must not fail the customer's payment.
                    log.exception(
                        "could not publish %s to the %s topic", case.case_id, cases_topic()
                    )

        if existing is not None:
            # The transaction already has a case. Leave its status, analyst_decision, summary
            # and citations alone, record the repeat on the timeline, and do not publish again.
            await cases_service.record_reevaluation(store, case.case_id, resp, resp.audit_id)
            log.info(
                "re-evaluated %s; existing case %s kept as is", req.transaction_id, case.case_id
            )

    return resp
