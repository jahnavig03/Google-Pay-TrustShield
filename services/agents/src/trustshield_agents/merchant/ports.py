"""PayGuard's two external dependencies. Adapters: extractors.py and ledgers.py."""

from __future__ import annotations

from typing import Protocol

from .models import Extraction, LedgerEntry


class ScreenshotExtractor(Protocol):
    """Reads amount, txn id, VPA, time and tamper hints off a payment screenshot."""

    name: str

    async def extract(self, uri: str) -> Extraction: ...


class MerchantLedger(Protocol):
    """The merchant's own ledger (trustshield.merchant_ledger in gcp mode)."""

    name: str

    async def find(self, merchant_id: str, txn_id: str) -> LedgerEntry | None: ...
