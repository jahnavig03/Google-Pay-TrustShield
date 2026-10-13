from __future__ import annotations

from enum import StrEnum
from typing import Protocol

from pydantic import BaseModel, Field


class ScamPattern(StrEnum):
    URGENCY = "urgency"
    FAKE_KYC = "fake_kyc"
    FAKE_REFUND = "fake_refund"
    RECEIVE_MONEY_FIRST = "receive_money_first"
    IMPERSONATION = "impersonation"
    QR_SWAP = "qr_swap"
    NONE = "none"


class ScamAssessment(BaseModel):
    """Structured output of the Scam Context agent (also the Gemini response schema)."""

    scam_probability: float = Field(ge=0, le=1)
    pattern: ScamPattern
    manipulation_cues: list[str] = Field(default_factory=list)
    safe_next_step: str


class ScamClassifier(Protocol):
    name: str

    async def classify(self, text: str) -> ScamAssessment: ...
