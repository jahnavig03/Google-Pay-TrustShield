"""Scam Context classifier on Gemini (Vertex AI) with a JSON response schema (gcp mode)."""

from __future__ import annotations

import hashlib
import logging
import threading
import time
from collections import OrderedDict

from google.genai import types

from ..ports.scam_classifier import ScamAssessment
from ..prompts import load_prompt
from .gemini_caller import GeminiCaller
from .rule_scam_classifier import RuleScamClassifier

log = logging.getLogger(__name__)


class _TTLCache:
    """Tiny LRU + TTL cache: identical messages (e.g. a replayed demo script) cost one call."""

    def __init__(self, ttl_s: float, max_items: int = 512):
        self._ttl_s, self._max = ttl_s, max_items
        self._data: OrderedDict[str, tuple[float, ScamAssessment]] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: str) -> ScamAssessment | None:
        with self._lock:
            hit = self._data.get(key)
            if hit is None or time.monotonic() - hit[0] > self._ttl_s:
                self._data.pop(key, None)
                return None
            self._data.move_to_end(key)
            return hit[1]

    def put(self, key: str, value: ScamAssessment) -> None:
        with self._lock:
            self._data[key] = (time.monotonic(), value)
            self._data.move_to_end(key)
            while len(self._data) > self._max:
                self._data.popitem(last=False)


class GeminiScamClassifier:
    name = "gemini"

    def __init__(
        self,
        caller: GeminiCaller,
        fallback: RuleScamClassifier,
        thinking: types.ThinkingConfig | None = None,
        cache_ttl_s: float = 0,
    ):
        self.caller = caller
        self._fallback = fallback
        self._thinking = thinking
        self._template = load_prompt("scam_context")
        self._cache = _TTLCache(cache_ttl_s) if cache_ttl_s > 0 else None

    def _key(self, text: str) -> str:
        raw = f"{self.caller.model}\x00{self._template}\x00{text}"
        return hashlib.sha256(raw.encode()).hexdigest()

    async def classify(self, text: str) -> ScamAssessment:
        if not (text or "").strip():
            return await self._fallback.classify(text)
        key = self._key(text)
        if self._cache and (cached := self._cache.get(key)) is not None:
            self.caller.stats.cache_hits += 1
            return cached
        try:
            resp = await self.caller.generate(
                contents=self._template.format(message=text),
                config=types.GenerateContentConfig(
                    temperature=0.0,
                    response_mime_type="application/json",
                    response_schema=ScamAssessment,
                    max_output_tokens=1024,
                    thinking_config=self._thinking,
                ),
            )
            if isinstance(resp.parsed, ScamAssessment):
                result = resp.parsed
            else:
                result = ScamAssessment.model_validate_json(resp.text or "")
        except Exception as exc:  # noqa: BLE001 — the payment path must not fail on the LLM
            log.warning("Gemini scam classification failed, using rules: %s", str(exc)[:300])
            return await self._fallback.classify(text)
        if self._cache:
            self._cache.put(key, result)
        return result
