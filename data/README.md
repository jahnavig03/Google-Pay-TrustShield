# data/: synthetic data generator + BigQuery

**Owner: Ronak.** SYNTHETIC data only: no real people, VPAs, phone numbers or Google Pay data.

## Quick start

```bash
cd data
python3 -m venv .venv && source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install --prefer-binary -r requirements.txt
python -m generator --seed 42                             # ~10 s
pytest
```

`python -m generator --seed 42` writes:

- `data/out/<table>.parquet` + `.csv` (gitignored, regenerate any time) and `data/out/manifest.json`
- `services/agents/data/mock/features.json` (committed; the agents' mock feature store)
- `services/agents/data/mock/merchant_ledger.json` + `screenshots.json` (committed; PayGuard mocks, see below)

Same seed means byte-identical files (`tests/test_determinism.py`). Options: `--out DIR`,
`--features PATH`, `--no-features`.

After changing anything in `generator/`, re-run it and commit the new `features.json`.
`tests/test_features.py` fails if the committed copy is stale. Then check the agents still pass:
`cd services/agents && .venv/bin/pytest`.

## What's in it

The world as of `AS_OF = 2026-10-13 21:00 IST`, covering the 90 days before it:

| Table | Rows | What |
| --- | --- | --- |
| `accounts` | 2,095 | 2,000 users, 50 merchants, 30 scammer VPAs, 15 mule accounts (`account_type`) |
| `devices` | ~2.6k | device / phone history per account (`device_id`, opaque `phone_id`, `first_seen`) |
| `transactions` | 50,000 | payments with channel, device, city/lat/lon, `device_changed`, `location_changed`, `beneficiary_age_minutes`, `message_context` |
| `beneficiaries` | ~27.5k | when each payer added each payee |
| `labels` | 50,000 | ground truth per transaction: `is_scam`, `scam_type`, `ring_id`, `is_hard_negative`, `hard_negative_type`, `reported_by_user`, `reported_at` |
| `merchants` | 50 | incl. the demo merchants `MER-DEMO-0042` (`mer.demo0042@synthbank`) and `chai.ramesh@synthbank` |
| `merchant_ledger` | ~27k | every credit to a merchant (`settled` / `pending`) + refunds, with `refund_abuse_pattern` |

Timestamps are UTC (microseconds) so they load straight into BigQuery `TIMESTAMP`.

**Scam archetypes** (`labels.scam_type`): `urgency`, `fake_kyc`, `fake_refund`,
`receive_money_first` (collect requests), `qr_swap` (swapped shop QR; `intended_payee_vpa` is the
shop the payer meant to pay). Victims add the scam VPA minutes before paying, some pay twice in an
hour, and some pay from a device they never used before. About 55% report it to the bank
(`reported_by_user`).

**Mule rings** (`ring_id`): `ring_a` is live today (16 victims in the last 24 h into one collector
VPA); `ring_b` ran 20–55 days ago. Members share 3 handsets and 2 SIMs, and money hops between
them (`scam_type = mule_layering`).

**Hard negatives** (`is_hard_negative`): monthly rent to a long-standing landlord (often 10–25x the
payer's median), school fees, wedding / birthday gifts to old contacts, hospital deposits to a
new payee, and ~450 payments to new but genuine payees (plumber, tutor, bill split).

**Refund abuse** (`merchant_ledger.refund_abuse_pattern`): `serial_refunder`,
`refund_exceeds_original`, `refund_to_different_vpa`, `duplicate_refund`.

## features.json

Exactly the schema the agents' `JsonFeatureStore` reads. Definitions (the BigQuery views
`v_payer_features` / `v_payee_features` compute the same):

| Field | Definition (as of AS_OF) |
| --- | --- |
| `median_amount` | exact median of the payer's outgoing amounts in the window |
| `avg_daily_txn` | outgoing count / 90 |
| `txn_count_1h` / `txn_count_24h` | outgoing count in the last 1 h / 24 h |
| `flags` | `reported_by_users` (a payment into it was reported), `vpa_created_recently` (created ≤ 7 days ago) |
| `reported_links` | distinct *other* accounts sharing a device or phone with the payee that received a payment labelled `is_scam` |
| `fan_in_24h` | distinct payers into the payee in the last 24 h |
| `is_merchant` | `account_type = 'merchant'` |

The demo rows (`payer_demo_001..004` and the six demo payees) are **pinned**. They come verbatim
from `generator/pinned_features.json` and always win over generated rows, because the demo
fixtures and the agents' tests depend on them. Generated VPAs always contain digits, so they can
never collide with the hand-written VPAs in tests and evals (e.g. `friend.regular@synthbank`).

## PayGuard mocks

- **`merchant_ledger.json`:** every ledger entry from the last 30 days for 4 merchants, including the demo
  merchant `MER-DEMO-0042`, copied unchanged from `merchant_ledger`. Mock mode and BigQuery mode
  therefore agree.
- **`screenshots.json`:** what OCR / Gemini "reads" off 30 synthetic screenshots, keyed by URI:
  `amount`, `txn_id`, `vpa`, `timestamp`, `tamper_hints`, plus `shown_at`. The `_case` field holds
  the test labels. There are 11 genuine screenshots (8 settled, 3 pending) and 19 fakes:
  - demo 3, plus 5 more with tamper hints
  - 4 with a made-up transaction id
  - 4 with an edited amount
  - 2 with an edited VPA
  - 3 reused old screenshots
- **Demo 3 is pinned exactly as in the fixture.** Its transaction id is reserved, so it never
  appears in any ledger. `tests/test_payguard_mocks.py` checks this.

## BigQuery (`data/bq/`)

```bash
gcloud auth login && gcloud auth application-default login
gcloud auth application-default set-quota-project qualified-sun-511214-t1
cd data && python -m generator --seed 42 --no-features   # data/out/ (incl. meta + demo tables)
bash bq/load.sh --dry-run                                  # prints every command, changes nothing
bash bq/load.sh                                            # create tables, batch-load, create views
python bq/verify.py                                        # views == features.json, row by row
```

**What `load.sh` does:**
- Creates the dataset if it's missing, then the tables in `bq/schema/*.sql` (`CREATE TABLE IF NOT EXISTS`).
- Empties each table with `TRUNCATE` and batch-loads the Parquet file with `bq load`.
- Creates both views in `bq/views/*.sql` (`CREATE OR REPLACE`).

**Cost rule:**
- Only batch `bq load` (free), never streaming.
- Every query is `--dry_run` first, and its byte count is printed.
- The whole dataset is about 5 MB, well inside the free tier.

`GCP_PROJECT_ID`, `GCP_REGION` and `BQ_DATASET` come from the environment or the repo-root `.env`.

| Object | What |
| --- | --- |
| `transactions`, `beneficiaries`, `devices`, `labels`, `merchant_ledger`, `accounts`, `merchants` | the generated tables, clustered for the lookups the agents and PayGuard make |
| `meta` | one row holding the dataset's `as_of`, the window, and `recent_vpa_days` |
| `demo_payer_features`, `demo_payee_features` | the pinned demo rows |
| `v_payer_features(payer_id, median_amount, avg_daily_txn, txn_count_1h, txn_count_24h)` | features.json `payers` |
| `v_payee_features(payee_vpa, flags ARRAY<STRING>, reported_links, fan_in_24h, is_merchant)` | features.json `payees` |

The views compute "now" as `meta.as_of`, not `CURRENT_TIMESTAMP()`, because the synthetic history
ends at `AS_OF`. Live traffic would swap in `CURRENT_TIMESTAMP()`. The views also union in the
pinned demo rows, so demo 1 behaves the same with `TRUSTSHIELD_FEATURE_STORE=bigquery`.
`tests/test_bq.py` checks offline that the DDL matches the Parquet schemas and that the SQL
never hard-codes a project.

## Held-out eval messages

`evals/heldout_messages.jsonl` contains 100 new labelled messages (65 English, 35 Hinglish), in the same
schema as `evals/scam_messages.jsonl`: 75 scams across `urgency`, `fake_kyc`, `fake_refund`,
`receive_money_first`, `impersonation` and `qr_swap`, plus 25 legitimate-but-urgent hard
negatives. They were written without looking at `services/agents/config/scam_rules.yaml`, so they
are a fair held-out test for the classifier. `tests/test_heldout_messages.py` checks the schema
and that no text overlaps the existing set.
