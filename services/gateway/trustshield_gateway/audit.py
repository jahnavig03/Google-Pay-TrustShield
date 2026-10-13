"""Governance rule 4: every decision gets an audit_id and an append-only ``audit_log`` row."""

from __future__ import annotations

from datetime import UTC, datetime

from trustshield_contracts import AuditRecord, GovernanceOutcome

from .ids import new_audit_id
from .ports import DocumentStore

AUDIT_COLLECTION = "audit_log"


def now() -> datetime:
    return datetime.now(UTC)


async def write_audit(
    store: DocumentStore,
    *,
    actor_type: str,
    actor_id: str,
    action: str,
    subject_type: str,
    subject_id: str,
    governance_outcome: GovernanceOutcome,
    decision: str | None = None,
    risk_score: float | None = None,
    evidence_ids: list[str] | None = None,
    approval_record_id: str | None = None,
    reason: str | None = None,
    audit_id: str | None = None,
) -> AuditRecord:
    """Build one :class:`AuditRecord`, write it to ``audit_log`` and return it."""
    record = AuditRecord(
        audit_id=audit_id or new_audit_id(),
        timestamp=now(),
        actor_type=actor_type,
        actor_id=actor_id,
        action=action,
        subject_type=subject_type,
        subject_id=subject_id,
        decision=decision,
        risk_score=risk_score,
        evidence_ids=list(evidence_ids or []),
        approval_record_id=approval_record_id,
        governance_outcome=governance_outcome,
        reason=reason,
    )
    await store.create(AUDIT_COLLECTION, record.audit_id, record.model_dump(mode="json"))
    return record
