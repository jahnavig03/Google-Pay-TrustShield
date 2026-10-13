"""PayGuard: POST /api/v1/merchant/payment-verify."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from trustshield_contracts import GovernanceOutcome, MerchantVerifyRequest, MerchantVerifyResponse

from .. import governance, merchant_service
from ..audit import write_audit
from ..deps import StoreDep
from ..governance import HTTP_422_BLOCKED
from ..ids import new_audit_id
from ..security import MERCHANT, require_role

router = APIRouter(prefix="/api/v1", tags=["payguard"])

ACTION = "merchant_verify"


@router.post(
    "/merchant/payment-verify",
    response_model=MerchantVerifyResponse,
    operation_id="verifyMerchantPayment",
    summary="Check a payment screenshot against the merchant ledger",
    dependencies=[Depends(require_role(MERCHANT))],
)
async def verify_merchant_payment(
    req: MerchantVerifyRequest, store: StoreDep
) -> MerchantVerifyResponse:
    resp, evidence_ids = await merchant_service.verify_merchant_payment(req)

    try:
        verdict = governance.review(
            evidence_ids=evidence_ids,
            customer_message=f"{resp.explanation} {resp.recommended_action}",
            decision=None,
        )
    except governance.GovernanceBlocked as blocked:
        record = await write_audit(
            store,
            actor_type="merchant",
            actor_id=req.merchant_id,
            action=ACTION,
            subject_type="merchant_verification",
            subject_id=req.claimed_transaction_id,
            decision=resp.payment_status.value,
            evidence_ids=evidence_ids,
            governance_outcome=GovernanceOutcome.BLOCKED,
            reason=blocked.reason,
        )
        raise HTTPException(
            HTTP_422_BLOCKED,
            detail={
                "governance_outcome": GovernanceOutcome.BLOCKED.value,
                "code": blocked.code,
                "reason": blocked.reason,
                "audit_id": record.audit_id,
            },
        ) from blocked

    resp.audit_id = new_audit_id()
    await write_audit(
        store,
        audit_id=resp.audit_id,
        actor_type="merchant",
        actor_id=req.merchant_id,
        action=ACTION,
        subject_type="merchant_verification",
        subject_id=req.claimed_transaction_id,
        decision=resp.payment_status.value,
        evidence_ids=evidence_ids,
        governance_outcome=verdict.outcome,
        reason=verdict.reason,
    )
    return resp
