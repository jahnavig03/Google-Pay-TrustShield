"""Resilient Gemini calls inside standard pay-as-you-go capacity (no Provisioned Throughput).

Gemini 2.5 Flash on Vertex AI draws on capacity shared by all customers, so a 429 means "busy
right now", not "your quota is used up", and there is no quota to raise. Following Google's 429
guidance, every call:
  1. is paced locally (GEMINI_MAX_QPS) so we never send bursts,
  2. retries 429 / 5xx with truncated exponential backoff and full jitter,
  3. alternates between the regional endpoint and a fallback location (GEMINI_FALLBACK_LOCATION,
     default `global`; same per-token price),
  4. stays inside one overall budget (GEMINI_TIMEOUT_MS). If the budget runs out, the adapter
     falls back to rules / templates, so a payment never fails because of the LLM.
Failed 429 requests are not billed, so retries add no cost unless they succeed.
"""

from __future__ import annotations

import asyncio
import logging
import random
import threading
import time
from dataclasses import dataclass, field

from google import genai
from google.genai import errors, types

log = logging.getLogger(__name__)

RETRYABLE_STATUS = {429, 500, 503, 504}
MIN_ATTEMPT_S = 0.25  # don't start an attempt with less time than this left


class GeminiUnavailable(RuntimeError):
    """Gemini could not answer within the budget; callers fall back to rules / templates."""


@dataclass
class GeminiStats:
    calls: int = 0
    succeeded: int = 0
    retries: int = 0
    fallback_location_used: int = 0
    rate_limited_responses: int = 0
    local_pacing_waits: int = 0
    gave_up: int = 0
    cache_hits: int = 0
    last_errors: list[str] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"{self.calls} Gemini requests · {self.succeeded} ok · {self.retries} retries · "
            f"{self.rate_limited_responses} × 429 · {self.fallback_location_used} on fallback "
            f"location · {self.gave_up} gave up → rules/templates · {self.cache_hits} cache hits"
        )


class GeminiCaller:
    def __init__(
        self,
        endpoints: list[tuple[str, genai.Client]],
        model: str,
        *,
        budget_ms: int = 2500,
        max_attempts: int = 3,
        max_qps: float = 4.0,
        backoff_base_ms: int = 150,
    ):
        if not endpoints:
            raise ValueError("at least one (location, client) endpoint is required")
        self.endpoints = endpoints
        self.model = model
        self._budget_s = budget_ms / 1000
        self._max_attempts = max(1, max_attempts)
        self._interval_s = 1.0 / max_qps if max_qps > 0 else 0.0
        self._backoff_base_s = backoff_base_ms / 1000
        self._lock = threading.Lock()  # evaluate_payment may run on several threads / loops
        self._next_slot = 0.0
        self.stats = GeminiStats()

    async def _pace(self, deadline: float) -> None:
        if not self._interval_s:
            return
        with self._lock:
            now = time.monotonic()
            slot = max(now, self._next_slot)
            if slot > deadline - MIN_ATTEMPT_S:
                raise GeminiUnavailable("local rate limit: no request slot inside the budget")
            self._next_slot = slot + self._interval_s
        if slot > now:
            self.stats.local_pacing_waits += 1
            await asyncio.sleep(slot - now)

    def _note_error(self, message: str) -> None:
        self.stats.last_errors = (self.stats.last_errors + [message[:200]])[-5:]

    async def generate(
        self, contents: str, config: types.GenerateContentConfig
    ) -> types.GenerateContentResponse:
        deadline = time.monotonic() + self._budget_s
        for attempt in range(self._max_attempts):
            location, client = self.endpoints[attempt % len(self.endpoints)]
            remaining = deadline - time.monotonic()
            if remaining < MIN_ATTEMPT_S:
                break
            await self._pace(deadline)
            remaining = deadline - time.monotonic()
            self.stats.calls += 1
            if attempt:
                self.stats.retries += 1
            if location != self.endpoints[0][0]:
                self.stats.fallback_location_used += 1
            try:
                resp = await asyncio.wait_for(
                    client.aio.models.generate_content(
                        model=self.model, contents=contents, config=config
                    ),
                    timeout=remaining,
                )
                self.stats.succeeded += 1
                return resp
            except TimeoutError:
                self._note_error(f"{location}: timed out")
                break  # the budget is spent
            except errors.APIError as exc:
                self._note_error(f"{location}: {exc.code} {str(exc)[:120]}")
                if exc.code == 429:
                    self.stats.rate_limited_responses += 1
                if exc.code not in RETRYABLE_STATUS:
                    self.stats.gave_up += 1
                    raise
                log.info("Gemini %s on %s (attempt %d), retrying", exc.code, location, attempt + 1)
            # truncated exponential backoff with full jitter, never past the deadline
            backoff = random.uniform(0, self._backoff_base_s * 2**attempt)
            await asyncio.sleep(max(0.0, min(backoff, deadline - time.monotonic() - MIN_ATTEMPT_S)))
        self.stats.gave_up += 1
        raise GeminiUnavailable(
            "no Gemini answer within budget: " + "; ".join(self.stats.last_errors[-2:])
        )
