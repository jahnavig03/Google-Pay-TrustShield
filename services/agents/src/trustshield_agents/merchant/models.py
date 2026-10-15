"""What PayGuard reads off a screenshot, what the ledger holds, and the rule thresholds."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from enum import StrEnum
from functools import lru_cache

import yaml
from pydantic import BaseModel, Field

from ..paths import config_dir

IST = timezone(timedelta(hours=5, minutes=30))


class TamperHint(StrEnum):
    """Visual / logical signs a screenshot may have been edited."""

    FONT_MISMATCH = "font_mismatch"
    EDITED_REGION = "edited_region"
    MISALIGNED_TEXT = "misaligned_text"
    UNUSUAL_LAYOUT = "unusual_layout"
    FUTURE_TIMESTAMP = "future_timestamp"  # added by the rules, never by the extractor


class Extraction(BaseModel):
    """Payment details read off one screenshot. Any field may be unreadable (None)."""

    amount: float | None = None
    txn_id: str | None = None
    vpa: str | None = None
    timestamp: datetime | None = None
    tamper_hints: list[TamperHint] = Field(default_factory=list)
    shown_at: datetime | None = None  # when it was shown / uploaded; default: now
    source: str = "none"  # mock | gemini | none (unreadable)


class LedgerEntry(BaseModel):
    """One row of trustshield.merchant_ledger."""

    merchant_id: str
    merchant_vpa: str
    entry_type: str  # credit | refund
    txn_id: str
    amount: float
    counterparty_vpa: str
    initiated_at: datetime
    settled_at: datetime | None = None
    status: str  # settled | pending


class MerchantRules(BaseModel):
    amount_tolerance: float = 0.5
    time_tolerance_minutes: float = 15
    stale_after_hours: float = 24
    future_tolerance_seconds: float = 60


@lru_cache(maxsize=1)
def load_rules() -> MerchantRules:
    path = config_dir() / "merchant.yaml"
    return MerchantRules.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")) or {})


def as_aware(ts: datetime | None) -> datetime | None:
    """Receipts without a zone are Indian time."""
    if ts is None or ts.tzinfo is not None:
        return ts
    return ts.replace(tzinfo=IST)
