# services/gateway — FastAPI on Cloud Run

**Owner: Hitesh.** REST `/api/v1`, the **Governance** module and the append-only Firestore
`audit_log`. Risk scoring itself lives in `services/agents`; the gateway never re-implements it,
and the agents service never implements Governance.

## Run it

```bash
cd services/gateway
python3 -m venv .venv && source .venv/bin/activate          # Python 3.11+
pip install --prefer-binary -r requirements.txt -e ../../shared/contracts -e ../agents
pytest
uvicorn main:app --reload --port 8000                        # http://localhost:8000/docs
```

`TRUSTSHIELD_MODE=mock` (the default) needs no GCP credentials.

## Routes

| Method | Path | Role (`X-Demo-Role`) |
| --- | --- | --- |
| GET | `/health` → `{"status": "ok"}` | none |
| POST | `/api/v1/payment-risk/evaluate` | `customer` |
| POST | `/api/v1/merchant/payment-verify` | `merchant` |
| GET | `/api/v1/cases` | `analyst` |
| GET | `/api/v1/cases/{case_id}` | `analyst` |
| POST | `/api/v1/cases/{case_id}/ask` | `analyst` |
| POST | `/api/v1/cases/{case_id}/decision` | `analyst` |

A missing role header is `401`, the wrong role is `403`. Every request and response type comes
from `shared/contracts`; `tests/test_contract_routes.py` fails if a route drifts from the registry
in `trustshield_contracts.api.ENDPOINTS`.

### `POST /api/v1/payment-risk/evaluate`

```
evaluate_payment_async(req)  ->  governance.review  ->  case + Pub/Sub  ->  audit row  ->  response
```

`HOLD_AND_ESCALATE` is returned to the customer as a **recommendation** (`200`: payment paused,
case opened), never as an error. The hold itself is executed only after an analyst approves it, so
the audit row for a hold is `governance_outcome = needs_approval`.

Any response with `analyst_case_required = true` (R ≥ 0.70) opens a case in Firestore `cases` with
status `pending_approval`, publishes `{"case_id": ...}` to the Pub/Sub `cases` topic and comes back
with `case_id` set.

### The other three

`POST /api/v1/merchant/payment-verify` is a placeholder that answers `not_found_in_ledger` /
`medium`. It sits behind `merchant_service.verify_merchant_payment`, which switches to
`trustshield_agents.verify_merchant_payment` as soon as Ronak's version exists.

`POST /api/v1/cases/{id}/ask` answers exactly `not covered by policy` with no citations until
Jahnavi's Investigator lands: nothing is retrieved yet, so nothing may be claimed.

`POST /api/v1/cases/{id}/decision` writes the approval record, then moves the case:
`approve_escalation` → `escalated`, `customer_outreach` → `customer_outreach`, `close` → `closed`.

## Governance (`governance.py`)

The four rules from `CLAUDE.md`, each with a section in `tests/test_governance.py`.

| Rule | Where | Failure |
| --- | --- | --- |
| 1. Hold / restrict / escalate need a human approval record | `require_approval()`, called by the decision flow | `409` |
| 2. No `evidence_ids` → the action is blocked | `review()`, before anything is returned | `422` + `blocked` audit row |
| 3. A customer message naming a PIN, OTP, password, CVV or card number is blocked, never cleaned up | `review()` | `422` + `blocked` audit row |
| 4. Every decision gets an `audit_id` and an `audit_log` row | `audit.write_audit()` | — |

A `422` body carries `{governance_outcome, code, reason, audit_id}`: the block is itself auditable.

## Ports and adapters

| Port | mock | gcp |
| --- | --- | --- |
| `DocumentStore` (`audit_log`, `cases`, `approvals`) | Firestore emulator when `FIRESTORE_EMULATOR_HOST` is set, otherwise an in-process store | Firestore (`asia-south1`) |
| `Publisher` (`cases` topic) | no-op publisher that records what it was handed | Pub/Sub |

`TRUSTSHIELD_DOC_STORE` (`firestore` / `memory`) and `TRUSTSHIELD_PUBLISHER` (`pubsub` / `noop`)
override the choice. Defaulting to the in-process store means `pytest` needs neither Java nor the
Firebase CLI, which is what keeps the Cloud Build test step simple.

## Tests

```bash
pytest                       # 74 tests, no emulator needed
                             # 75 with the Firestore emulator running (see below)
```

`tests/test_payment_flow.py` drives the ₹85,000 fixture
(`shared/contracts/fixtures/demo1_payment_85k.json`) end to end and asserts `HOLD_AND_ESCALATE`,
`analyst_case_required = true`, a non-empty `audit_id` and `case_id`, the audit row and the
pending case. The same flow runs against the real Firestore emulator in
`test_85k_fixture_writes_to_the_firestore_emulator`, which skips itself unless the emulator is
reachable:

```bash
firebase emulators:start --only firestore        # needs Java 21+, reads firebase.json
FIRESTORE_EMULATOR_HOST=localhost:8080 pytest    # 75 passed, 0 skipped
```

Verified on 14 Oct 2026 against firebase-tools 15.33.0 and the Firestore emulator v1.22.0: the
₹85,000 fixture writes a real `audit_log` row (`payment_risk_decision`, `HOLD_AND_ESCALATE`,
`needs_approval`) and a `pending_approval` case. Change the port in `firebase.json` and `.env`
together if 8080 is taken.

## Container

Built **from the repo root** — the image needs `shared/contracts` and `services/agents` too.

```bash
docker build -f services/gateway/Dockerfile -t trustshield-gateway .
docker run --rm -p 8080:8080 -e TRUSTSHIELD_MODE=mock trustshield-gateway
```

`python:3.11-slim`, listens on `$PORT` (8080 by default), runs as a non-root user.
