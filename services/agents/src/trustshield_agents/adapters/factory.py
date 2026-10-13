"""Build the adapter set for the current TRUSTSHIELD_MODE."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from typing import TYPE_CHECKING

from ..ports import CustomerMessageWriter, EvidenceProvider, FeatureStore, ScamClassifier
from ..settings import feature_store_backend, mode, require_env
from .json_feature_store import JsonFeatureStore
from .rule_scam_classifier import RuleScamClassifier
from .static_evidence import StaticEvidenceProvider
from .template_message_writer import TemplateMessageWriter

if TYPE_CHECKING:
    from .gemini_caller import GeminiCaller


@dataclass(frozen=True)
class Services:
    mode: str
    features: FeatureStore
    scam: ScamClassifier
    evidence: EvidenceProvider
    messages: CustomerMessageWriter
    gemini: GeminiCaller | None = None  # gcp mode: call stats for demos / evals


def _feature_store() -> FeatureStore:
    if feature_store_backend() == "bigquery":
        from .bigquery_feature_store import BigQueryFeatureStore

        return BigQueryFeatureStore(
            require_env("GCP_PROJECT_ID"), os.environ.get("BQ_DATASET", "trustshield")
        )
    return JsonFeatureStore()


@lru_cache(maxsize=2)
def _build(current_mode: str) -> Services:
    rules = RuleScamClassifier()
    templates = TemplateMessageWriter()
    if current_mode == "mock":
        return Services("mock", _feature_store(), rules, StaticEvidenceProvider(), templates)

    import google.auth
    from google import genai
    from google.auth.exceptions import DefaultCredentialsError
    from google.genai import types

    from .gemini_caller import GeminiCaller
    from .gemini_message_writer import GeminiMessageWriter
    from .gemini_scam_classifier import GeminiScamClassifier

    project, region = require_env("GCP_PROJECT_ID"), require_env("GCP_REGION")
    model = require_env("GEMINI_FAST_MODEL")
    # Resolve credentials once, up front: otherwise every Gemini call re-probes for them
    # (~6 s each) before falling back to rules.
    try:
        credentials, _ = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
    except DefaultCredentialsError as exc:
        raise RuntimeError(
            "TRUSTSHIELD_MODE=gcp needs Application Default Credentials: run "
            "`gcloud auth application-default login`, or use TRUSTSHIELD_MODE=mock"
        ) from exc
    budget_ms = int(os.environ.get("GEMINI_TIMEOUT_MS", "2500"))

    def client_for(location: str) -> genai.Client:
        return genai.Client(
            vertexai=True,
            project=project,
            location=location,
            credentials=credentials,
            # Hard cap per request; GeminiCaller enforces the overall budget across retries.
            http_options=types.HttpOptions(timeout=budget_ms),
        )

    # Regional first (lowest latency from India); on 429 / 5xx the caller retries on the
    # fallback location. Both are standard pay-as-you-go at the same price: no extra billing.
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
    # Thinking adds ~3 s on gemini-2.5-flash; the live path runs with a 0 budget (no thinking).
    # (Gemini 3.x models use thinking_level instead; revisit if GEMINI_FAST_MODEL changes.)
    thinking = types.ThinkingConfig(
        thinking_budget=int(os.environ.get("GEMINI_FAST_THINKING_BUDGET", "0"))
    )
    return Services(
        "gcp",
        _feature_store(),
        GeminiScamClassifier(
            caller,
            rules,
            thinking,
            cache_ttl_s=float(os.environ.get("GEMINI_CACHE_TTL_S", "600")),
        ),
        StaticEvidenceProvider(),  # TODO(prompt 9 / RAG): Vertex AI Search evidence provider
        # A second sequential Gemini call adds ~1 s, which breaks the PRD latency SLO, so the
        # Gemini-written customer message is opt-in. Templates are evidence-backed and checked.
        GeminiMessageWriter(caller, templates, thinking)
        if os.environ.get("GEMINI_CUSTOMER_MESSAGE", "template").strip().lower() == "llm"
        else templates,
        caller,
    )


def build_services() -> Services:
    return _build(mode())
