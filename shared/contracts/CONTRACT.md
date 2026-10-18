# Contract frozen — v0.3.0 (18 Oct 2026: `POST /translate` added; v0.2.0 added optional `qr`)
Source of truth: `shared/contracts` (Pydantic v2). TS types: `npx openapi-typescript shared/contracts/openapi.json -o web/src/api/schema.ts`.
Fixtures for the 3 demo stories: `shared/contracts/fixtures/*.json`. Changes need agreement from all four of us.
**Request** (`POST /api/v1/payment-risk/evaluate`): unchanged + optional `attachment_uri` and `qr` (`{raw, payee_name?, amount?, merchant_code?}`, v0.2). Now validated: `amount > 0`, `beneficiary_age_minutes >= 0`.
**Response** keeps `risk_score, decision, risk_type, customer_message, analyst_case_required, evidence_ids` (same names/types; `decision` is the enum ALLOW | WARN | STEP_UP_VERIFICATION | HOLD_AND_ESCALATE). Added, all with defaults:
- `top_signals: [{code, label, plain_explanation, contribution}]` (max 5)
- `safe_actions: [{code, label}]`, code ∈ cancel_payment | verify_recipient | report_scam | contact_bank_official | proceed
- `case_id: str | null`, `audit_id: str | null` (gateway Governance fills `audit_id`)
**Merchant** `POST /api/v1/merchant/payment-verify`: `{merchant_id, uploaded_screenshot, claimed_amount, claimed_transaction_id}` → `{payment_status, risk_level, extracted?, recommended_action, explanation, audit_id?}`.
**Cases**: `GET /cases`, `GET /cases/{id}`, `POST /cases/{id}/ask` (`{question}` → `{answer, citations}`), `POST /cases/{id}/decision` (`{action, analyst_id, reason}` → `{case_id, status, decision}`).
**Audit**: `AuditRecord` = one row of Firestore `audit_log`. Empty retrieval → answer is exactly `"not covered by policy"`.
**Translate** `POST /api/v1/translate` (v0.3): `{target_language, texts[≤100]}` → `{target_language, translations, provider}`. Languages: en hi bn te mr ta gu kn ml pa or. Cloud Translation in gcp mode; mock returns the text unchanged.
