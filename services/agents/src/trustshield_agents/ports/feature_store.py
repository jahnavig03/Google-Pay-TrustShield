from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, Field


class PayerFeatures(BaseModel):
    median_amount: float | None = None
    avg_daily_txn: float = 2.0
    txn_count_1h: int = 0
    txn_count_24h: int = 0


class PayeeFeatures(BaseModel):
    flags: list[str] = Field(default_factory=list)
    reported_links: int = 0
    fan_in_24h: int = 0
    is_merchant: bool = False


class FeatureStore(Protocol):
    """Behavioural features per payer / payee (BigQuery feature views in gcp mode)."""

    async def payer(self, payer_id: str) -> PayerFeatures: ...

    async def payee(self, payee_vpa: str) -> PayeeFeatures: ...
