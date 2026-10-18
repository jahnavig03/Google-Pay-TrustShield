"""QR-code checks for payments whose payee came from a scanned / uploaded UPI QR.

The customer's device decodes the QR; we get the raw text plus the fields it held. Three checks,
each a manipulation cue that feeds the Scam Context signal (S):

  qr_not_upi_payment     the code isn't a UPI payment (e.g. a website link)
  qr_name_mismatch       the name printed in the QR isn't the UPI ID's registered owner
                         (the classic swapped-sticker scam at a shop counter)
  qr_merchant_unverified the QR carries a merchant code, but the UPI ID isn't a registered merchant
"""

from __future__ import annotations

import math
import re

from pydantic import BaseModel, Field
from trustshield_contracts import QrPayload

from .ports import ScamAssessment, ScamPattern

# Probability each finding adds to S (combined with noisy-OR). Config-style constants, kept here
# because they describe how the QR checks themselves are calibrated, not the risk thresholds.
CUE_PROBABILITY = {
    "qr_not_upi_payment": 0.9,
    "qr_name_mismatch": 0.85,
    "qr_merchant_unverified": 0.6,
}
SAFE_NEXT_STEP = (
    "Scanning a QR code sends money. Check that the name shown matches who you mean to pay, "
    "or ask the shop to confirm their UPI ID."
)
_STOPWORDS = {"the", "and", "store", "stores", "shop", "mr", "mrs", "ms", "sri", "shri"}


class QrAssessment(BaseModel):
    probability: float = Field(ge=0, le=1)
    cues: list[str] = Field(default_factory=list)


def _tokens(name: str) -> set[str]:
    return {t for t in re.findall(r"[a-z]+", name.lower()) if len(t) >= 3 and t not in _STOPWORDS}


def names_match(qr_name: str, registered: str) -> bool:
    """Lenient match: any shared meaningful word ('Ramesh Tea Stall' ~ 'Ramesh Tea Stall Pvt')."""
    return bool(_tokens(qr_name) & _tokens(registered))


def assess_qr(
    qr: QrPayload | None, registered_name: str | None, payee_is_merchant: bool
) -> QrAssessment | None:
    if qr is None:
        return None
    cues: list[str] = []
    if not qr.raw.strip().lower().startswith("upi://pay"):
        cues.append("qr_not_upi_payment")
    if qr.payee_name and registered_name and not names_match(qr.payee_name, registered_name):
        cues.append("qr_name_mismatch")
    if qr.merchant_code and not payee_is_merchant:
        cues.append("qr_merchant_unverified")
    survive = math.prod(1 - CUE_PROBABILITY[c] for c in cues)
    return QrAssessment(probability=round(1 - survive, 4), cues=cues)


def merge_qr(scam: ScamAssessment, qr: QrAssessment | None) -> ScamAssessment:
    """Fold QR findings into the Scam Context result (noisy-OR on the probability)."""
    if qr is None or not qr.cues:
        return scam
    probability = 1 - (1 - scam.scam_probability) * (1 - qr.probability)
    qr_leads = qr.probability >= scam.scam_probability or scam.pattern is ScamPattern.NONE
    return ScamAssessment(
        scam_probability=round(min(probability, 0.99), 4),
        pattern=ScamPattern.QR_SWAP if qr_leads else scam.pattern,
        manipulation_cues=[*qr.cues, *[c for c in scam.manipulation_cues if c not in qr.cues]],
        safe_next_step=SAFE_NEXT_STEP if qr_leads else scam.safe_next_step,
    )
