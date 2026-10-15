"""verify_merchant_payment(req) -> MerchantVerifyResponse: PayGuard's entry point for the gateway.

| | TRUSTSHIELD_MODE=mock | TRUSTSHIELD_MODE=gcp |
| --- | --- | --- |
| Screenshot | data/mock/screenshots.json | Gemini (GEMINI_FAST_MODEL) reads the image; falls back to the mock |
| Ledger | data/mock/merchant_ledger.json | BigQuery `<GCP_PROJECT_ID>.<BQ_DATASET>.merchant_ledger`; on error, the JSON |

TRUSTSHIELD_MERCHANT_LEDGER=json|bigquery overrides the ledger (default: json in mock, bigquery
in gcp). Gemini gets GEMINI_VISION_TIMEOUT_MS (default 5000: the PRD's image p95 < 5 s) and
GEMINI_VISION_THINKING_BUDGET (default: GEMINI_FAST_THINKING_BUDGET, i.e. 0).
audit_id is left empty: the gateway's Governance fills it in.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache

from trustshield_contracts import MerchantVerifyRequest, MerchantVerifyResponse

from ..settings import mode, require_env
from .extractors import GeminiScreenshotExtractor, MockScreenshotExtractor
from .ledgers import BigQueryMerchantLedger, FallbackLedger, JsonMerchantLedger, LedgerUnavailable
from .models import MerchantRules, load_rules
from .ports import MerchantLedger, ScreenshotExtractor
from .rules import decide

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class MerchantServices:
    extractor: ScreenshotExtractor
    ledger: MerchantLedger
    rules: MerchantRules


def _gemini_extractor(fallback: MockScreenshotExtractor) -> GeminiScreenshotExtractor:
    import google.auth
    from google import genai
    from google.genai import types

    from ..adapters.gemini_caller import GeminiCaller

    project, region = require_env("GCP_PROJECT_ID"), require_env("GCP_REGION")
    model = require_env("GEMINI_FAST_MODEL")
    credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    budget_ms = int(os.environ.get("GEMINI_VISION_TIMEOUT_MS", "5000"))

    def client_for(location: str) -> genai.Client:
        return genai.Client(
            vertexai=True,
            project=project,
            location=location,
            credentials=credentials,
            http_options=types.HttpOptions(timeout=budget_ms),
        )

    endpoints = [(region, client_for(region))]
    fallback_location = os.environ.get("GEMINI_FALLBACK_LOCATION", "global").strip()
    if fallback_location and fallback_location != region:
        endpoints.append((fallback_location, client_for(fallback_location)))
    caller = GeminiCaller(
        endpoints,
        model,
        budget_ms=budget_ms,
        max_attempts=int(os.environ.get("GEMINI_MAX_ATTEMPTS", "3")),
        max_qps=float(os.environ.get("GEMINI_MAX_QPS", "4")),
    )
    # Default: the live path's budget (0 = off). Live test 14 Oct: with thinking off, 2.5 Flash
    # reads every field but misses a swapped amount font; GEMINI_VISION_THINKING_BUDGET=2048
    # catches it at ~5 s per image (then raise GEMINI_VISION_TIMEOUT_MS to ~10000).
    budget = os.environ.get("GEMINI_VISION_THINKING_BUDGET") or os.environ.get(
        "GEMINI_FAST_THINKING_BUDGET", "0"
    )
    thinking = types.ThinkingConfig(thinking_budget=int(budget))
    return GeminiScreenshotExtractor(caller, fallback, thinking)


def _ledger(current_mode: str) -> MerchantLedger:
    default = "bigquery" if current_mode == "gcp" else "json"
    backend = os.environ.get("TRUSTSHIELD_MERCHANT_LEDGER", default).strip().lower()
    json_ledger = JsonMerchantLedger()
    if backend != "bigquery":
        return json_ledger
    bq = BigQueryMerchantLedger(
        require_env("GCP_PROJECT_ID"),
        os.environ.get("BQ_DATASET", "trustshield"),
        require_env("GCP_REGION"),
    )
    return FallbackLedger(bq, json_ledger)


@lru_cache(maxsize=2)
def build_merchant_services(current_mode: str | None = None) -> MerchantServices:
    current_mode = current_mode or mode()
    mock = MockScreenshotExtractor()
    extractor = _gemini_extractor(mock) if current_mode == "gcp" else mock
    return MerchantServices(extractor, _ledger(current_mode), load_rules())


async def verify_with(
    req: MerchantVerifyRequest, services: MerchantServices, now: datetime | None = None
) -> MerchantVerifyResponse:
    extraction = await services.extractor.extract(req.uploaded_screenshot)
    now = now or datetime.now(UTC)
    try:
        entry = await services.ledger.find(req.merchant_id, req.claimed_transaction_id)
        if entry is None and extraction.txn_id and extraction.txn_id != req.claimed_transaction_id:
            entry = await services.ledger.find(req.merchant_id, extraction.txn_id)
    except LedgerUnavailable as exc:
        log.warning("merchant ledger unavailable: %s", exc)
        return decide(req, extraction, None, services.rules, now, ledger_unavailable=True)
    return decide(req, extraction, entry, services.rules, now)


async def verify_merchant_payment(req: MerchantVerifyRequest) -> MerchantVerifyResponse:
    """Check a payment screenshot against the merchant's ledger. Leaves audit_id empty."""
    return await verify_with(req, build_merchant_services(mode()))
