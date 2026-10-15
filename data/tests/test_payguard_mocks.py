"""PayGuard mock files: the ledger is an exact slice of merchant_ledger; screenshots cover every case."""

import json
from collections import Counter

import pandas as pd
import pytest

from generator import config as C
from generator.output import DEFAULT_FEATURES
from generator.payguard import CASES, DEMO3, DEMO3_URI, build_payguard_mocks

MOCK_DIR = DEFAULT_FEATURES.parent


@pytest.fixture(scope="module")
def mocks(ds):
    return build_payguard_mocks(ds)


def test_ledger_is_an_exact_slice_of_the_bigquery_table(ds, mocks):
    ledger, _ = mocks
    table = ds["merchant_ledger"].set_index("txn_id")
    assert {e["merchant_id"] for e in ledger["entries"]} >= {"MER-DEMO-0042", "MER-DEMO-0007"}
    for e in ledger["entries"]:
        row = table.loc[e["txn_id"]]
        assert row["merchant_id"] == e["merchant_id"] and row["amount"] == e["amount"]
        assert row["status"] == e["status"] and row["entry_type"] == e["entry_type"]
        assert pd.Timestamp(e["initiated_at"]) == row["initiated_at"]


def test_demo3_is_pinned_and_its_txn_never_settles(mocks):
    ledger, shots = mocks
    assert shots["screenshots"][DEMO3_URI] == DEMO3
    assert all(e["txn_id"] not in C.RESERVED_TXN_IDS for e in ledger["entries"])


def test_screenshots_cover_every_case(mocks):
    _, shots = mocks
    kinds = Counter(s["_case"]["kind"] for s in shots["screenshots"].values())
    for kind, (count, _, _) in CASES.items():
        assert kinds[kind] == count, kind
    assert len(shots["screenshots"]) >= 20
    statuses = {s["_case"]["expected_status"] for s in shots["screenshots"].values()}
    assert statuses == {"verified", "pending", "inconsistent", "not_found_in_ledger", "suspicious"}


def test_fake_screenshot_ids_are_not_in_any_ledger(ds, mocks):
    _, shots = mocks
    real = set(ds["merchant_ledger"]["txn_id"])
    for shot in shots["screenshots"].values():
        case = shot["_case"]
        found = case["claimed_transaction_id"] in real
        assert found == (case["expected_status"] not in {"suspicious", "not_found_in_ledger"})


def test_committed_mock_files_are_up_to_date(mocks):
    """Fails if generator code changed without re-running `python -m generator --seed 42`."""
    ledger, shots = mocks
    assert json.loads((MOCK_DIR / "merchant_ledger.json").read_text(encoding="utf-8")) == ledger
    assert json.loads((MOCK_DIR / "screenshots.json").read_text(encoding="utf-8")) == shots
