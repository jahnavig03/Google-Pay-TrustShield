"""python -m trustshield_agents.demo1 — run the ₹85,000 fixture through the agent workflow.

Uses TRUSTSHIELD_MODE (default mock: no credentials needed). Prints the response and latency.
"""

from __future__ import annotations

import asyncio
import json
import statistics
import time

from trustshield_contracts import PaymentRiskRequest
from trustshield_contracts.fixtures import DEMO1_PAYMENT, load_fixture

from .diagnostics import watch_fallbacks
from .service import evaluate_payment_async
from .settings import mode

WARM_RUNS = 5


async def _main() -> None:
    req = PaymentRiskRequest.model_validate(load_fixture(DEMO1_PAYMENT)["request"])
    fallbacks = watch_fallbacks()

    t0 = time.perf_counter()
    resp = await evaluate_payment_async(req)
    cold_ms = (time.perf_counter() - t0) * 1000

    warm = []
    for _ in range(WARM_RUNS):
        t0 = time.perf_counter()
        await evaluate_payment_async(req)
        warm.append((time.perf_counter() - t0) * 1000)

    print(f"TRUSTSHIELD_MODE={mode()}  ·  Prototype simulator — synthetic data\n")
    print(json.dumps(resp.model_dump(mode="json"), indent=2, ensure_ascii=False))
    print(
        f"\nlatency: first call {cold_ms:.0f} ms (includes adapter set-up)  ·  "
        f"warm p50 {statistics.median(warm):.0f} ms, max {max(warm):.0f} ms over {WARM_RUNS} runs"
    )
    if mode() == "gcp":
        from .adapters.factory import build_services

        gemini = build_services().gemini
        if gemini is not None:
            print(f"Gemini: {gemini.stats.summary()}")
            if gemini.stats.cache_hits:
                print(
                    "  (warm runs were answered from the verdict cache; "
                    "set GEMINI_CACHE_TTL_S=0 to time Gemini itself)"
                )
        if fallbacks.messages:
            print(f"\n⚠ {len(fallbacks.messages)} Gemini fallback(s) to rules/templates, e.g.:")
            print(f"  {fallbacks.messages[0][:300]}")
        else:
            print("Gemini: every call succeeded (no fallbacks).")


def main() -> None:
    asyncio.run(_main())


if __name__ == "__main__":
    main()
