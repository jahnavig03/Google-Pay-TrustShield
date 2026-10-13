"""PayGuard: POST /api/v1/merchant/payment-verify."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class PaymentStatus(StrEnum):
    VERIFIED = "verified"
    PENDING = "pending"
    INCONSISTENT = "inconsistent"
    NOT_FOUND_IN_LEDGER = "not_found_in_ledger"
    SUSPICIOUS = "suspicious"


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class MerchantVerifyRequest(BaseModel):
    merchant_id: str
    uploaded_screenshot: str = Field(
        description="gs:// or https:// URI of the screenshot, or a data: URI with base64 image."
    )
    claimed_amount: float = Field(gt=0)
    claimed_transaction_id: str


class ExtractedPaymentDetails(BaseModel):
    """What OCR / Gemini vision read off the screenshot. Any field may be unreadable."""

    amount: float | None = None
    txn_id: str | None = None
    vpa: str | None = None
    timestamp: datetime | None = None


class MerchantVerifyResponse(BaseModel):
    payment_status: PaymentStatus
    risk_level: RiskLevel
    extracted: ExtractedPaymentDetails | None = None
    recommended_action: str
    explanation: str
    audit_id: str | None = Field(default=None, description="Filled in by gateway Governance.")
