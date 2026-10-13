"""FeatureStore backed by data/mock/features.json (mock mode, and gcp mode until BigQuery is ready)."""

from __future__ import annotations

import json
from pathlib import Path

from ..paths import mock_data_dir
from ..ports.feature_store import PayeeFeatures, PayerFeatures


class JsonFeatureStore:
    def __init__(self, path: Path | None = None):
        data = json.loads((path or mock_data_dir() / "features.json").read_text(encoding="utf-8"))
        defaults = data.get("defaults", {})
        self._payers = data.get("payers", {})
        self._payees = data.get("payees", {})
        self._default_payer = PayerFeatures.model_validate(defaults.get("payer", {}))
        self._default_payee = PayeeFeatures.model_validate(defaults.get("payee", {}))

    async def payer(self, payer_id: str) -> PayerFeatures:
        row = self._payers.get(payer_id)
        return PayerFeatures.model_validate(row) if row else self._default_payer

    async def payee(self, payee_vpa: str) -> PayeeFeatures:
        row = self._payees.get(payee_vpa.lower())
        return PayeeFeatures.model_validate(row) if row else self._default_payee
