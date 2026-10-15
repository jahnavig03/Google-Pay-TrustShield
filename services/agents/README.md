# services/agents — TrustShield agent layer

**Owner: Jahnavi.** Google ADK orchestrator, Transaction Risk + Scam Context agents, risk-fusion
engine, prompts. Governance and audit logging are **not** here; the gateway owns them.

## Integration (gateway `main.py`)

```python
from trustshield_agents import evaluate_payment_async  # or evaluate_payment (sync)
from trustshield_contracts import PaymentRiskRequest, PaymentRiskResponse


@app.post("/api/v1/payment-risk/evaluate", response_model=PaymentRiskResponse)
async def evaluate(req: PaymentRiskRequest) -> PaymentRiskResponse:
    return governance.apply(await evaluate_payment_async(req))  # Governance fills audit_id
```

Call `await trustshield_agents.warm_up_async()` once at start-up (the gateway's lifespan does). It
builds the adapters, compiles the workflow and opens the Gemini connections with a free metadata
call, so the first payment after a cold start doesn't pay ~2-3 s of set-up.

Install into the gateway venv: `pip install --prefer-binary -e ../agents -e ../../shared/contracts`.
The response always has `top_signals` (3–5) and `evidence_ids`. `audit_id` and `case_id` are left
empty for the gateway to fill in. `evaluate_payment` (sync) also works inside a running event loop.

## Setup

```bash
cd services/agents
python3 -m venv .venv && source .venv/bin/activate      # Python 3.11+
pip install --prefer-binary -r requirements.txt -e ../../shared/contracts -e .
pytest
python -m trustshield_agents.risk demo     # risk engine only, ₹85k fixture
python -m trustshield_agents.demo1         # full ADK workflow + latency (mock mode)
adk web adk_apps                           # http://localhost:8000 — send JSON, or plain text
```

`--prefer-binary` avoids building `cryptography` from source on machines without Rust.

## How it works

```
START -> parse_request -> ( transaction_risk || scam_context ) -> join_signals -> fuse_decision
```

An ADK 2.x graph `Workflow` (see `orchestrator.py`). ADK 2.x deprecates `SequentialAgent` and
`ParallelAgent` in favour of `Workflow`: the tuple in the edge chain runs both specialists in
parallel, and `JoinNode` waits for both.

| Node | Port → adapters (mock / gcp) |
| --- | --- |
| Transaction Risk | `FeatureStore` → `JsonFeatureStore` (`data/mock/features.json`) / `BigQueryFeatureStore` (stub, TODO) |
| Scam Context | `ScamClassifier` → `RuleScamClassifier` (`config/scam_rules.yaml`) / `GeminiScamClassifier` (`GEMINI_FAST_MODEL`, JSON schema, falls back to rules) |
| Fusion | risk engine (`risk/`, `config/risk.yaml`) + `EvidenceProvider` → `StaticEvidenceProvider` (`config/evidence.yaml`) + `CustomerMessageWriter` → templates / Gemini with guardrails |

Risk: `R = sigmoid(bias + Σ w·x)` over A, B, D, L, V, S, N. Each feature has a documented
normalisation function in `risk/features.py`. Weights, thresholds and per-org overrides
(`TRUSTSHIELD_ORG_ID`) are in `config/risk.yaml`, which also explains the calibration.

## Modes

| | `TRUSTSHIELD_MODE=mock` (default) | `TRUSTSHIELD_MODE=gcp` |
| --- | --- | --- |
| Scam Context | keyword/regex rules | Gemini on Vertex AI (`gemini-2.5-flash`, `asia-south1`, thinking off) |
| Customer message | templates | templates by default; `GEMINI_CUSTOMER_MESSAGE=llm` for Gemini (adds ~1 s), guardrail-checked |
| Features | JSON fixture | JSON fixture (`TRUSTSHIELD_FEATURE_STORE=bigquery` once views exist) |
| Evidence | static mapping | static mapping (Vertex AI Search next) |

gcp mode needs `GCP_PROJECT_ID`, `GCP_REGION`, `GEMINI_FAST_MODEL` and Application Default
Credentials (`gcloud auth application-default login`). It fails fast at start-up if any are missing.
The repo-root `.env` is loaded automatically. Gemini calls time out after `GEMINI_TIMEOUT_MS`
(default 2500) and fall back to rules or templates; `demo1` and the evals report every fallback.

Findings from live calls on project `qualified-sun-511214-t1` (13 Oct 2026):
- In `asia-south1` only `gemini-2.5-flash` is served. `gemini-3.8-flash`, `gemini-2.5-flash-lite`
  and the Pro models return 404 there; Pro works on `global` (`GEMINI_PRO_LOCATION`, ~3–5 s).
- 2.5 Flash thinks by default (~4 s per call). `GEMINI_FAST_THINKING_BUDGET=0` brings it to ~1 s.
- `gemini-2.5-flash` runs on standard pay-as-you-go capacity shared by all customers. A 429 means
  "busy", there is no project quota to raise, and we don't buy Provisioned Throughput.
  `adapters/gemini_caller.py` stays inside that capacity: it paces requests (`GEMINI_MAX_QPS`),
  retries 429/5xx with jittered backoff, tries `GEMINI_FALLBACK_LOCATION` (`global`, same price),
  and keeps everything inside `GEMINI_TIMEOUT_MS`. Identical messages reuse the last verdict for
  `GEMINI_CACHE_TTL_S`. Anything left over falls back to rules, so no payment fails.
- Eval run (80 payments, 70 Gemini requests): p50 862 ms, p95 1.08 s, no 429s. One slow call ran
  past the budget and used rules. Meets the PRD's p95 < 2 s; p50 is just above the 800 ms target.

## PayGuard merchant check (`merchant/`, owner: Ronak)

```python
from trustshield_agents import verify_merchant_payment  # async; the gateway picks it up

resp = await verify_merchant_payment(MerchantVerifyRequest(...))  # audit_id left empty
```

| Port | mock | gcp |
| --- | --- | --- |
| `ScreenshotExtractor` | `data/mock/screenshots.json` (by URI) | Gemini `GEMINI_FAST_MODEL` reads the image (gs://, https:// or data: URI), JSON schema, via `gemini_caller.py`; any failure falls back to the mock |
| `MerchantLedger` | `data/mock/merchant_ledger.json` | BigQuery `trustshield.merchant_ledger` (REST, parameterised; on error falls back to the JSON). `TRUSTSHIELD_MERCHANT_LEDGER=json` forces the JSON |

**Rules** (`merchant/rules.py`, thresholds in `config/merchant.yaml`):

| `payment_status` | When | Risk |
| --- | --- | --- |
| `verified` | the transaction is in the merchant's ledger, amount, VPA and time match, and it has settled | low |
| `pending` | found and matching, but not settled yet | medium |
| `inconsistent` | found, but the amount, VPA, transaction id or time differs, it is a refund, or it is an old payment shown again | high if the amount differs or it is a refund, else medium |
| `not_found_in_ledger` | not found, no sign of editing | medium |
| `suspicious` | not found, plus tamper hints (font mismatch, edited region, or a timestamp after the time it was shown) | high |

The ledger is the source of truth. The text is merchant-facing and neutral, and never mentions credentials.
Both mock files are generated by `data/` (`python -m generator --seed 42`). The mock ledger is an
exact slice of the BigQuery table. The tests cover every status, demo 3 (`suspicious`/`high`,
word for word), and 100% detection on the 30 synthetic screenshots (PRD target: at least 90%).

**Live check (14 Oct, gcp mode):**
- **Gemini 2.5 Flash reads every field of a synthetic receipt correctly** in about 2–4 s.
- **The BigQuery ledger returns the same rows as the mock,** in about 0.5 s per lookup once warm.
- **With `thinking_budget` 0, Gemini misses a swapped amount font.** Setting `GEMINI_VISION_THINKING_BUDGET=2048` catches it, at about 5 s per image; if you enable it, also set `GEMINI_VISION_TIMEOUT_MS=10000`. The payment path is unaffected either way.
- **Demo 3's fixture URI points at a bucket that doesn't exist,** so gcp mode falls back to the mock and still returns `suspicious`/`high`.

## Layout

```
config/     risk.yaml, scam_rules.yaml, evidence.yaml, prompts.yaml
prompts/    versioned prompt templates (<name>.<version>.md)
data/mock/  features.json, merchant_ledger.json, screenshots.json (generated by data/)
adk_apps/   `adk web` entry point
src/trustshield_agents/
  orchestrator.py  service.py  fusion.py  demo1.py  guardrails.py
  risk/            engine, features, explanations, config loader, `python -m ... demo`
  ports/           FeatureStore, ScamClassifier, EvidenceProvider, CustomerMessageWriter
  adapters/        mock + gcp implementations, factory.py
```
