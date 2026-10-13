"""PayInvestigator cases + audit records.

Endpoints:
  GET  /api/v1/cases                 -> CaseListResponse
  GET  /api/v1/cases/{case_id}       -> Case
  POST /api/v1/cases/{case_id}/ask   CaseQuestion -> CaseAnswer
  POST /api/v1/cases/{case_id}/decision   AnalystDecisionRequest -> CaseDecisionResponse
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from .payment import Decision, Signal

NOT_COVERED_BY_POLICY = "not covered by policy"


class CaseStatus(StrEnum):
    OPEN = "open"
    PENDING_APPROVAL = "pending_approval"
    ESCALATED = "escalated"
    CUSTOMER_OUTREACH = "customer_outreach"
    CLOSED = "closed"


class AnalystAction(StrEnum):
    APPROVE_ESCALATION = "approve_escalation"
    CUSTOMER_OUTREACH = "customer_outreach"
    CLOSE = "close"


class EntityType(StrEnum):
    ACCOUNT = "account"
    VPA = "vpa"
    DEVICE = "device"
    PHONE = "phone"
    MERCHANT = "merchant"


class TimelineEvent(BaseModel):
    timestamp: datetime
    event_type: str = Field(examples=["message_received", "beneficiary_added", "payment_initiated"])
    description: str
    evidence_id: str | None = None


class LinkedEntity(BaseModel):
    entity_type: EntityType
    entity_id: str
    relation: str = Field(examples=["payee", "shares_device_with_payee"])
    risk_note: str | None = None


class PolicyCitation(BaseModel):
    """A retrieved policy passage. Every policy claim must point at one of these."""

    evidence_id: str
    title: str
    snippet: str
    uri: str | None = None


class AnalystDecision(BaseModel):
    action: AnalystAction
    analyst_id: str
    reason: str
    decided_at: datetime
    audit_id: str | None = None


class Case(BaseModel):
    case_id: str
    transaction_id: str
    created_at: datetime
    status: CaseStatus = CaseStatus.OPEN
    risk_score: float = Field(ge=0, le=1)
    decision: Decision
    risk_type: str
    summary: str
    top_signals: list[Signal] = Field(default_factory=list)
    timeline: list[TimelineEvent] = Field(default_factory=list)
    linked_entities: list[LinkedEntity] = Field(default_factory=list)
    citations: list[PolicyCitation] = Field(default_factory=list)
    recommended_action: AnalystAction | None = None
    missing_evidence: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    analyst_decision: AnalystDecision | None = None


class CaseSummary(BaseModel):
    """Row in the analyst case list."""

    case_id: str
    transaction_id: str
    created_at: datetime
    status: CaseStatus
    risk_score: float = Field(ge=0, le=1)
    decision: Decision
    risk_type: str
    amount: float
    payee_vpa: str


class CaseListResponse(BaseModel):
    cases: list[CaseSummary]


class CaseQuestion(BaseModel):
    question: str = Field(min_length=1, examples=["Why was this payment flagged?"])


class CaseAnswer(BaseModel):
    """Grounded answer. With no retrieved citations the answer is NOT_COVERED_BY_POLICY."""

    answer: str
    citations: list[PolicyCitation] = Field(default_factory=list)


class AnalystDecisionRequest(BaseModel):
    action: AnalystAction
    analyst_id: str
    reason: str = Field(min_length=1)


class CaseDecisionResponse(BaseModel):
    case_id: str
    status: CaseStatus
    decision: AnalystDecision


class GovernanceOutcome(StrEnum):
    PERMITTED = "permitted"
    NEEDS_APPROVAL = "needs_approval"
    BLOCKED = "blocked"


class AuditRecord(BaseModel):
    """One row in the Firestore ``audit_log`` collection (append-only, written by the gateway)."""

    audit_id: str
    timestamp: datetime
    actor_type: str = Field(examples=["system", "analyst", "merchant"])
    actor_id: str
    action: str = Field(examples=["payment_risk_decision", "analyst_decision", "merchant_verify"])
    subject_type: str = Field(examples=["payment", "case", "merchant_verification"])
    subject_id: str
    decision: str | None = None
    risk_score: float | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    approval_record_id: str | None = None
    governance_outcome: GovernanceOutcome
    reason: str | None = None
