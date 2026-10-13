"""FeatureStore backed by BigQuery feature views (gcp mode). Stub until the views exist."""

from __future__ import annotations

from ..ports.feature_store import PayeeFeatures, PayerFeatures


class BigQueryFeatureStore:
    def __init__(self, project_id: str, dataset: str):
        self.project_id = project_id
        self.dataset = dataset

    async def payer(self, payer_id: str) -> PayerFeatures:
        # TODO(Jahnavi + Ronak): query Ronak's payer feature view, e.g.
        #   SELECT median_amount, avg_daily_txn, txn_count_1h, txn_count_24h
        #   FROM `{project_id}.{dataset}.v_payer_features` WHERE payer_id = @payer_id
        # via google-cloud-bigquery (run in a thread; cache hot payers in Firestore per PRD §8).
        raise NotImplementedError(
            "BigQuery feature views not wired yet; use TRUSTSHIELD_FEATURE_STORE=json"
        )

    async def payee(self, payee_vpa: str) -> PayeeFeatures:
        # TODO(Jahnavi + Ronak): `{project_id}.{dataset}.v_payee_features` (flags, mule-link count,
        # 24h fan-in, is_merchant) keyed by payee_vpa.
        raise NotImplementedError(
            "BigQuery feature views not wired yet; use TRUSTSHIELD_FEATURE_STORE=json"
        )
