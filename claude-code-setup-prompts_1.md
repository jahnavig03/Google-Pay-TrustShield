# TrustShield: Claude Code setup prompts (v2)

**The split this version follows**
- **Hitesh**: gateway + Governance + Firestore `audit_log` + Dockerfile, following the "Steps ahead" doc.
- **Jahnavi**: contract, risk engine, ADK agents, prompts and evals. These are prompts 0–4 and 9 below.
- **Sameer** and **Ronak**: prompts 6 and 7 are reference specs for them.
- **Integration (14 Oct)**: the gateway's fake scoring is swapped for `agents.evaluate_payment()`.

**Agreed conventions**
- Health check: `/health`.
- Python: plain `venv` + pip.
- A PIN/OTP request in a customer message is **blocked**.
- R ≥ 0.90 → `HOLD_AND_ESCALATE`.

**How to use this**
1. Put `CLAUDE.md` and `Google_Pay_TrustShield_PRD.md` in the repo root, then start `claude` there.
2. Run one prompt per session, or `/clear` between them. Use **plan mode** (Shift+Tab) for prompts 1 and 4, and review the plan before approving it.
3. Check the "Done when" list yourself, then commit.

---

## YOUR TRACK (Jahnavi)

### Prompt 0: Check your machine
```
Check my local dev environment for this project and tell me what's missing. Don't install anything without asking.
Need: Python 3.11+, Git, Node.js LTS, npm, Firebase CLI (firebase-tools), Java 17 (for the Firestore/Pub/Sub emulators), Docker Desktop, Google Cloud CLI (gcloud), VS Code.
For each item, show the version found or "missing", plus the exact macOS install command (Homebrew preferred; Firebase CLI via `npm install -g firebase-tools`; Java 17 via Temurin).
Then show me the gcloud commands to: log in, set the project, and set up application-default credentials. I'll run them once our GCP project ID is ready.
Finally, confirm `firebase emulators:start --only firestore` can start, then stop it.
```

### Prompt 1: Repo skeleton (only if Hitesh hasn't created it yet)
```
Read CLAUDE.md and Google_Pay_TrustShield_PRD.md fully. Create the monorepo folders exactly as laid out in CLAUDE.md: web/, services/gateway/, services/agents/, shared/contracts/, data/, infra/, evals/.

- Root: .gitignore (Python, .venv, Node, .env, GCP key files, emulator data), .editorconfig, .env.example listing every env var with comments, and a README with the pitch, the architecture mermaid copied from the PRD, the folder/owner map and local setup steps.
- shared/contracts and services/agents: each gets a pyproject.toml (installable with pip install -e), a requirements.txt, a src/ layout and one passing pytest.
- Leave services/gateway, web/, data/ and infra/ as README placeholders that name the owner. Teammates fill those in.
- Use plain venv + pip, not uv or poetry.

Done when: in services/agents, `python3 -m venv .venv && source .venv/bin/activate && pip install -e ../../shared/contracts -e . && pytest` passes. Show me the tree.
```

### Prompt 2: Freeze the API contract
```
Build shared/contracts as Pydantic v2 models. This is the single source of truth for the API.

The request must stay compatible with the gateway Hitesh already has:
transaction_id: str, amount: float, currency: str = "INR", payer_id: str, payee_vpa: str, beneficiary_age_minutes: int, device_changed: bool = False, location_changed: bool = False, message_context: str | None = None.
Add only optional fields on top: attachment_uri: str | None.

1. POST /api/v1/payment-risk/evaluate
   Response: risk_score, decision (enum ALLOW | WARN | STEP_UP_VERIFICATION | HOLD_AND_ESCALATE), risk_type, top_signals (list of {code, label, plain_explanation, contribution}), customer_message, safe_actions (list), analyst_case_required, case_id (optional), evidence_ids, audit_id (optional; filled in by gateway Governance).
   Keep the keys Hitesh's fake response already returns (risk_score, decision, risk_type, customer_message, analyst_case_required, evidence_ids) with the same names and types.
2. POST /api/v1/merchant/payment-verify
   Request: merchant_id, uploaded_screenshot, claimed_amount, claimed_transaction_id.
   Response: payment_status (verified | pending | inconsistent | not_found_in_ledger | suspicious), risk_level, extracted (amount, txn_id, vpa, timestamp — optional), recommended_action, explanation, audit_id (optional).
3. Case models: Case, TimelineEvent, LinkedEntity, PolicyCitation, AnalystDecision (approve_escalation | customer_outreach | close), AuditRecord.
4. Endpoint shapes: GET /api/v1/cases, GET /api/v1/cases/{id}, POST /api/v1/cases/{id}/ask (question → grounded answer + citations), POST /api/v1/cases/{id}/decision.

Also:
- Add JSON fixtures for the 3 demo stories in shared/contracts/fixtures/: the ₹85,000 "account will be blocked" scam, the analyst case, and the fake ₹12,000 screenshot.
- Add a script that exports openapi.json, so Sameer can generate TypeScript types.
- Add tests that validate every fixture against the models.

Done when: tests pass and openapi.json exists. Then write a short CONTRACT.md (≤ 15 lines) I can paste to the team as "contract frozen". It should list every field added on top of the gateway's current response.
```

### Prompt 3: Risk-fusion engine
```
In services/agents, build a pure-Python risk-fusion module with no GCP dependencies.

- Feature inputs, each normalised to 0–1 with its own documented function:
  A amount deviation (vs the payer's median), B beneficiary risk (age in minutes + flags), D device anomaly, L location anomaly, V velocity, S scam-context probability, N mule-network risk.
- R = sigmoid(Σ w_i·x_i + bias). Load weights, bias and thresholds from config/risk.yaml, with per-org override support. Use the thresholds in CLAUDE.md.
- Output: the decision enum, plus the top 3–5 signals ranked by contribution (w_i·x_i). Each signal gets a plain-language, non-accusatory explanation from a template, e.g. "The recipient was added 4 minutes ago."
- R ≥ 0.70 sets analyst_case_required = true.
- Tests:
  (a) The ₹85,000 fixture scores ≥ 0.90 → HOLD_AND_ESCALATE, with new beneficiary, amount deviation, device change and urgency language in the top signals.
  (b) A normal ₹500 payment to a long-standing payee → ALLOW.
  (c) Hard negatives: a large but legitimate rent payment to an old payee must not hold. A new but genuine payee with a small amount must not hold.
  (d) Exact threshold boundaries.
- Calibrate the default weights so these tests pass, and explain them in a comment.

Done when: pytest passes and `python -m trustshield_agents.risk demo` prints the ₹85k decision with its signals.
```

### Prompt 4: ADK agents (Demo 1 path)
```
First check the installed google-adk version and read its current docs/API. Then build the agent layer in services/agents with ADK.
Do NOT implement Governance or audit logging. The gateway (Hitesh) owns those.

- Orchestrator (root agent): takes a PaymentRiskRequest from shared/contracts. It runs Transaction Risk and Scam Context in parallel, fuses their results with the risk engine, and returns a PaymentRiskResponse with top_signals and evidence_ids always filled in. Leave audit_id empty.
- Transaction Risk: gets features through a FeatureStore port. The mock adapter reads data/mock/features.json (create a small one now for the demo payer). The gcp adapter is a stub with a TODO to query Ronak's BigQuery feature views.
- Scam Context: uses Gemini (model from GEMINI_FAST_MODEL) on message_context. It returns scam_probability, pattern (urgency | fake_kyc | fake_refund | receive_money_first | impersonation | qr_swap | none), manipulation cues and a safe next step, as structured JSON. In mock mode, use a keyword/rule classifier so it runs without a key.
- Evidence IDs: for now, map each risk_type to static policy IDs (e.g. policy_payment_safety_01) from config. Prompt 9 / the RAG work replaces this with Vertex AI Search.
- Prompts go in services/agents/prompts/*.md, versioned, not inline strings. The customer-message prompt must be non-accusatory, give 1–2 safe actions, and never ask for a PIN, OTP, password or card number.
- Expose a plain function `evaluate_payment(req: PaymentRiskRequest) -> PaymentRiskResponse` that Hitesh's gateway can import. Document it in services/agents/README.md with a 5-line integration snippet for main.py.
- Make it work with `adk web` for local debugging.
- Add `python -m trustshield_agents.demo1`: run the ₹85k fixture in mock mode and pretty-print the response plus latency.

Done when: demo1 works with no credentials. With TRUSTSHIELD_MODE=gcp and Gemini creds set, it calls real Gemini. Report latency for both modes.
```

### Prompt 4b: Integration with the gateway (14 Oct, with Hitesh)
```
services/gateway/main.py currently returns fake scores. Replace the body of the /api/v1/payment-risk/evaluate handler with a call to trustshield_agents.evaluate_payment, then pass the result through the existing Governance module before responding.
Keep the route, request model and Governance code unchanged apart from importing the shared contract models.
Install the agents package into the gateway venv with `pip install -e ../agents -e ../../shared/contracts`.
Update the gateway tests so the ₹85,000 fixture returns HOLD_AND_ESCALATE, analyst_case_required = true, a non-empty audit_id, and a row in the Firestore emulator's audit_log collection.
```

### Prompt 9: Eval set and runner (16–17 Oct)
```
In evals/, build:
- scam_messages.jsonl: 40 synthetic messages (Indian UPI context, English and some Hinglish) across all scam patterns + 10 legitimate-but-urgent hard negatives, each labelled.
- payment_scenarios.jsonl: 30 payment scenarios with expected decision bands.
- tone_checks.py: rules that flag accusatory wording, any request for PIN/OTP/password, and missing safe actions.
- run_evals.py: runs everything through evaluate_payment (mock or gcp mode) and reports recall on high-risk cases, false-positive rate on hard negatives, pattern accuracy, tone violations, and p50/p95 latency. Output a markdown table against the PRD section-2 targets, saved to evals/results/<date>.md.
```

---

## TEAMMATE REFERENCE SPECS (share these; don't run them yourself)

### Prompt 5: Gateway (Hitesh — already covered by the "Steps ahead" doc)
The doc's steps are the source of truth. Make sure the final gateway also has:
- `/health`
- The merchant route with fake "not found in ledger" responses
- governance.py + test_governance.py enforcing the 4 Governance rules in CLAUDE.md
- Every decision written to the Firestore emulator `audit_log` collection
- A Dockerfile that is built **and run** locally
- CORS for localhost:5173
- An `X-Demo-Role` header stub for roles until Firebase Auth is added
- Hold/escalate without an approval record returns 409

### Prompt 6: Web app skeleton (Sameer)
```
Create web/ with React + Vite + TypeScript, React Router and TanStack Query. Generate types from shared/contracts/openapi.json with openapi-typescript. Add a typed API client with a base URL from VITE_API_BASE_URL (default http://localhost:8000).
Routes:
- /pay: payment simulator form (amount, payee VPA, new-payee toggle, device-changed toggle, paste-message box). On submit, show a warning sheet with the decision, top signals and safe actions (Cancel / Verify recipient / Report).
- /analyst: case list → case detail (timeline, signals, linked entities, citations, an "Ask why" box, Approve escalation / Outreach / Close buttons).
- /merchant: screenshot upload + claimed amount/txn ID → verdict card.
Add a persistent banner on every page: "Prototype simulator — synthetic data. Not affiliated with Google Pay." Use no Google Pay logo, colours or look-alike UI.
Add a demo-role switcher that sets the X-Demo-Role header.
Done when: all three demo stories click through against the local gateway.
```

### Prompt 7: Synthetic data and BigQuery (Ronak)
```
In data/, build a seeded synthetic data generator (Python + Faker):
- 2,000 users, 50k transactions over 90 days, device and location history.
- 5 labelled scam archetypes (urgency/account-block, fake KYC, fake refund, receive-money-first collect request, QR swap) + 2 mule rings (shared devices/phones receiving from many victims).
- Hard negatives: large legitimate payments, new genuine payees.
- A merchant ledger for 50 merchants (settled/pending) + refund-abuse patterns.
- Output Parquet + CSV to data/out/, and regenerate services/agents/data/mock/features.json in the same schema the agents use.
Also write BigQuery DDL (data/bq/schema/*.sql), feature views (amount deviation vs median, beneficiary age, 1h/24h velocity, device/location change, mule-link count) and data/bq/load.sh using bq with GCP_PROJECT_ID. The SQL is a dry run only until the project is ready.
```

### Prompt 8: GCP bootstrap and CI/CD (Hitesh)
```
In infra/, write idempotent bash scripts using only gcloud/bq/gsutil, parameterised by GCP_PROJECT_ID and GCP_REGION, each with a --dry-run flag:
1. enable-apis.sh: Vertex AI, BigQuery, Pub/Sub, Cloud Run, Firestore, Document AI, Discovery Engine, Cloud Build, Artifact Registry, Secret Manager, Storage, Logging/Monitoring.
2. bootstrap.sh: per-service service accounts with least privilege; an Artifact Registry repo; Pub/Sub topics payments, alerts, cases, reports; Firestore (native); GCS buckets for uploads, policy-docs, datasets; BigQuery dataset trustshield.
3. cloudbuild.yaml: test → build gateway (with the agents package) → push → deploy to Cloud Run (min-instances=1); build web → Firebase Hosting.
4. A README with the run order and how to connect the Cloud Build trigger to our Google Cloud repo.
```

### Prompt 10: Final check before submission (anyone, 17 Oct)
```
Review the whole repo as a strict senior engineer. Check:
- Each service installs and passes pytest from a clean clone.
- No secrets or keys are committed.
- .env.example is complete.
- The README setup steps work.
- The 4 Governance rules and every "Non-negotiable rule" in CLAUDE.md are enforced in code and covered by a test.
Fix the small issues, and list the rest as TODOs in the README.
```

---

### Tips
- If Claude Code drifts, say: "Re-read CLAUDE.md. Stay inside services/agents for this task."
- If an ADK or Vertex call fails, paste the full error and say: "Check the installed package version and current docs before changing code."
- Once the Google Cloud repo exists, add it as the remote and push: `git remote add origin <url> && git push -u origin main`.
