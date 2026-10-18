"""PaySafe Interceptor: POST /api/v1/payment-risk/evaluate."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class Decision(StrEnum):
    """Customer-facing outcome. Thresholds on R live in config, not here."""

    ALLOW = "ALLOW"
    WARN = "WARN"
    STEP_UP_VERIFICATION = "STEP_UP_VERIFICATION"
    HOLD_AND_ESCALATE = "HOLD_AND_ESCALATE"


class RiskType(StrEnum):
    """Known values for PaymentRiskResponse.risk_type.

    The field itself stays a plain ``str`` so the gateway's existing responses keep validating.
    """

    NONE = "none"
    URGENCY = "urgency"
    FAKE_KYC = "fake_kyc"
    FAKE_REFUND = "fake_refund"
    RECEIVE_MONEY_FIRST = "receive_money_first"
    IMPERSONATION = "impersonation"
    QR_SWAP = "qr_swap"
    MULE_NETWORK = "mule_network"
    BEHAVIOURAL_ANOMALY = "behavioural_anomaly"


class SafeActionCode(StrEnum):
    CANCEL_PAYMENT = "cancel_payment"
    VERIFY_RECIPIENT = "verify_recipient"
    REPORT_SCAM = "report_scam"
    CONTACT_BANK_OFFICIAL = "contact_bank_official"
    PROCEED = "proceed"


class Signal(BaseModel):
    """One explained risk signal. ``contribution`` is w_i·x_i from the risk engine."""

    code: str = Field(examples=["new_beneficiary"])
    label: str = Field(examples=["New recipient"])
    plain_explanation: str = Field(examples=["The recipient was added 4 minutes ago."])
    contribution: float


class SafeAction(BaseModel):
    code: SafeActionCode
    label: str = Field(examples=["Cancel this payment"])


class QrPayload(BaseModel):
    """What the customer's app decoded from a scanned / uploaded UPI QR code.

    Decoding happens on the device; only these fields are sent. A UPI QR holds
    ``upi://pay?pa=<vpa>&pn=<name>&am=<amount>&cu=INR&mc=<merchant code>``.
    """

    raw: str = Field(max_length=2048, description="The full decoded QR text.")
    payee_name: str | None = Field(default=None, max_length=120, description="pn= in the QR.")
    amount: float | None = Field(default=None, gt=0, description="am= in the QR, if fixed.")
    merchant_code: str | None = Field(
        default=None, max_length=8, description="mc= (merchant category code), if present."
    )


class PaymentRiskRequest(BaseModel):
    """Compatible with the gateway's original request; only optional fields are added."""

    transaction_id: str
    amount: float = Field(gt=0)
    currency: str = "INR"
    payer_id: str
    payee_vpa: str
    beneficiary_age_minutes: int = Field(ge=0)
    device_changed: bool = False
    location_changed: bool = False
    message_context: str | None = None
    # Added on top of the gateway's request:
    attachment_uri: str | None = Field(
        default=None,
        description="gs:// or https:// URI of an uploaded screenshot, QR or transcript.",
    )
    qr: QrPayload | None = Field(
        default=None, description="Set when the payee came from a scanned / uploaded QR code."
    )


class PaymentRiskResponse(BaseModel):
    """Decision returned to the customer app.

    Original gateway keys: risk_score, decision, risk_type, customer_message,
    analyst_case_required, evidence_ids. Everything else is additive and has a default.
    """

    risk_score: float = Field(ge=0, le=1)
    decision: Decision
    risk_type: str = Field(description="One of RiskType where possible.")
    customer_message: str
    analyst_case_required: bool
    evidence_ids: list[str] = Field(default_factory=list)
    # Added on top of the gateway's response:
    top_signals: list[Signal] = Field(default_factory=list, max_length=5)
    safe_actions: list[SafeAction] = Field(default_factory=list)
    case_id: str | None = None
    audit_id: str | None = Field(default=None, description="Filled in by gateway Governance.")
