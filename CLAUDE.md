# Google Pay TrustShield — project context for Claude Code

Hackathon entry for the Google Cloud AI Builder Cup, BFSI track. Submission is due **18 Oct 2026**, with feature freeze on 16 Oct.
The full spec is in `Google_Pay_TrustShield_PRD.md`. Read it before any large change.

## What we're building
This is a multi-agent safety layer for UPI that catches *authorized payments made under manipulation*. It has three modules:
- **PaySafe Interceptor** (customer): scores a payment, returns allow / warn / step-up / hold, and shows the top 3–5 signals in plain, non-accusatory language.
- **PayInvestigator** (analyst): auto-creates a case when R ≥ 0.70. It shows the timeline, linked accounts and cited policy, answers grounded Q&A, and requires human approval.
- **PayGuard** (merchant): checks a payment screenshot against the merchant ledger and returns verified / pending / inconsistent / suspicious.

## Monorepo layout and owners
```
web/                 React + Vite + TS. Routes /pay, /analyst, /merchant          — Sameer
services/gateway/    FastAPI on Cloud Run. REST /api/v1, Governance, audit log     — Hitesh
services/agents/     Google ADK. Orchestrator, Transaction Risk, Scam Context,
                     Investigator, Evidence & Policy agents; risk engine; prompts  — Jahnavi
shared/contracts/    Pydantic models = the API contract (source of truth)          — Jahnavi (changes agreed by all)
data/                Synthetic data generator, BigQuery schemas + feature views    — Ronak
infra/               Cloud Build, gcloud bootstrap scripts                         — Hitesh
evals/               Eval sets + runner                                            — Jahnavi
```
Keep changes inside your own area unless a contract change is agreed.

## How the pieces connect
The gateway receives the request and calls `agents.evaluate_payment(request)`. That returns a decision with `top_signals` and `evidence_ids`. The gateway's **Governance** module checks the result, assigns an `audit_id` and writes it to the Firestore `audit_log` collection, then responds.
The agents service does **not** implement Governance. It must always return `top_signals` and `evidence_ids` so Governance can check them.

## Stack and conventions
- Python 3.11+. Each service has its own `.venv` (`python3 -m venv .venv`) and a `requirements.txt`. `shared/contracts` is installed into each service with `pip install -e ../../shared/contracts`.
- Use FastAPI, Pydantic v2 and pytest. Lint and format with ruff.
- Node LTS for web/ and Firebase CLI. Java 21+ is required by the Firestore and Pub/Sub emulators (firebase-tools 15 dropped older Java).
- The health endpoint is `GET /health` → `{"status": "ok"}`.
- Google Cloud: Cloud Run, Pub/Sub, BigQuery (+BQML), Gemini on Vertex AI, Vertex AI Search, Document AI, Firestore, Cloud Storage, Secret Manager, Cloud Build. The default region is `asia-south1`. Code is hosted in Google Cloud repos.
- **Everything must run locally with no GCP credentials.** Set `TRUSTSHIELD_MODE=mock`:
  - Gemini is replaced by a deterministic rule-based fake.
  - BigQuery is replaced by JSON fixtures.
  - Firestore and Pub/Sub use the local emulators (`firebase emulators:start --only firestore`; set `FIRESTORE_EMULATOR_HOST=localhost:8080`).
  - `TRUSTSHIELD_MODE=gcp` uses the real services.
- Put every external dependency behind an interface (`ports/` + `adapters/`) so mock and gcp modes can be swapped.
- Never hard-code model names, project IDs or thresholds. Read them from env or config: `GEMINI_FAST_MODEL`, `GEMINI_PRO_MODEL`, `GCP_PROJECT_ID`, `GCP_REGION`.
- Before writing ADK or Vertex code, check the installed package version and current docs, because these APIs change often.

## Risk model (core logic, services/agents)
R = sigmoid(w1·A + w2·B + w3·D + w4·L + w5·V + w6·S + w7·N)
The inputs are A amount deviation, B beneficiary risk, D device anomaly, L location anomaly, V velocity, S scam-context probability, and N mule-network risk.
Thresholds are config, not code:

| R | Decision |
|---|---|
| < 0.35 | `ALLOW` |
| 0.35–0.70 | `WARN` |
| 0.70–0.90 | `STEP_UP_VERIFICATION` |
| ≥ 0.90 | `HOLD_AND_ESCALATE` |

Any R ≥ 0.70 opens a case (`analyst_case_required = true`).

## Governance rules (services/gateway, enforced in code + tests)
1. Hold, restrict and escalate require a human (analyst) approval record.
2. If there are no `evidence_ids`, the action is blocked.
3. Any customer message that asks for a PIN, OTP, password or full card number is **blocked**, not cleaned up.
4. Every decision gets an `audit_id` and is written to the Firestore `audit_log` collection.

## Non-negotiable rules
- Use synthetic data only. Never use real Google Pay data, identities or credentials.
- Customer-facing text must be non-accusatory and must give a safe next action.
- Every policy claim must cite a retrieved source. If nothing is retrieved, answer "not covered by policy".
- Every page shows the pinned banner "Built exclusively for the Google Cloud AI Builder Cup". The UI must not use Google or Google Pay logos or look like the real Google Pay app.
- Git: never add `Co-Authored-By` trailers, "Generated with Claude Code" lines or any other AI attribution to commit messages or PR descriptions. Commits are authored by the team member only.

## Commands (keep this section updated)
- Gateway install: `cd services/gateway && python3 -m venv .venv && source .venv/bin/activate && pip install --prefer-binary -r requirements.txt -e ../../shared/contracts -e ../agents`
- Gateway: `cd services/gateway && source .venv/bin/activate && uvicorn main:app --reload` → http://localhost:8000/docs
- Gateway roles: send `X-Demo-Role: customer | analyst | merchant` (evaluate / `/cases*` / merchant). Missing header → 401, wrong role → 403.
- Gateway image (build from the REPO ROOT): `docker build -f services/gateway/Dockerfile -t trustshield-gateway .` then `docker run --rm -p 8080:8080 -e TRUSTSHIELD_MODE=mock trustshield-gateway`
- Web: `cd web && npm install && npm run dev` → http://localhost:5173 (needs the gateway on :8000; Node 24). `npm test`, `npm run lint`, `npm run build`; `npm run gen:api` after any contract change.
- Web deploy: `cd web && VITE_API_BASE_URL=<cloud-run-url> npm run build && cd .. && firebase deploy --only hosting --project qualified-sun-511214-t1` (then add the Hosting URL to the gateway's `CORS_ALLOW_ORIGINS`)
- Agents install: `cd services/agents && python3 -m venv .venv && source .venv/bin/activate && pip install --prefer-binary -r requirements.txt -e ../../shared/contracts -e .`
- Agents demo: `cd services/agents && source .venv/bin/activate && python -m trustshield_agents.demo1`
- Risk engine demo: `python -m trustshield_agents.risk demo` (agents venv)
- ADK dev UI: `cd services/agents && adk web adk_apps` (ADK 2.x graph `Workflow`; Sequential/ParallelAgent are deprecated)
- Contract → OpenAPI: `cd shared/contracts && source .venv/bin/activate && python scripts/export_openapi.py` (re-run after any model change; a test fails if stale)
- Evals: `cd services/agents && source .venv/bin/activate && python ../../evals/run_evals.py [--mode gcp]` → `evals/results/<date>.md`
- Firestore emulator: `firebase emulators:start --only firestore` (needs Java 21+; use port 8081 and `FIRESTORE_EMULATOR_HOST=localhost:8081` if 8080 is taken)
- Infra: `bash infra/enable-apis.sh [--dry-run]` then `bash infra/bootstrap.sh [--dry-run]` (idempotent; `--dry-run` changes nothing)
- Cloud Build by hand: `gcloud builds submit --config cloudbuild.yaml --substitutions=SHORT_SHA=manual .` (a push to `main` runs it automatically)
- Tests: `pytest` inside each service (and `shared/contracts`). The gateway suite needs no emulator and no credentials; its one emulator test skips itself unless `FIRESTORE_EMULATOR_HOST` is reachable.
