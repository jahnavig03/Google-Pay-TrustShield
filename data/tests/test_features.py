"""features.json: exact schema the agents read, pinned demo rows, and the committed copy."""

import json

import pytest

from generator.features import DEFAULTS, build_features, dumps, load_pinned
from generator.output import DEFAULT_FEATURES

PAYER_KEYS = {"median_amount", "avg_daily_txn", "txn_count_1h", "txn_count_24h"}
PAYEE_KEYS = {"flags", "reported_links", "fan_in_24h", "is_merchant"}
ALLOWED_FLAGS = {"reported_by_users", "vpa_created_recently"}


@pytest.fixture(scope="module")
def features(ds):
    return build_features(ds)


def test_schema(features):
    assert features["schema_version"] == 1
    assert features["defaults"] == DEFAULTS
    for row in features["payers"].values():
        assert set(row) == PAYER_KEYS
        assert row["median_amount"] is None or row["median_amount"] > 0
        assert isinstance(row["txn_count_1h"], int) and isinstance(row["txn_count_24h"], int)
        assert row["txn_count_1h"] <= row["txn_count_24h"]
    for vpa, row in features["payees"].items():
        assert vpa == vpa.lower()
        assert set(row) == PAYEE_KEYS
        assert set(row["flags"]) <= ALLOWED_FLAGS
        assert isinstance(row["is_merchant"], bool)


def test_demo_rows_are_pinned_unchanged(features):
    pinned = load_pinned()
    assert sorted(pinned["payers"]) == [f"payer_demo_00{i}" for i in range(1, 5)]
    assert len(pinned["payees"]) == 6
    for key, row in pinned["payers"].items():
        assert features["payers"][key] == row
    for key, row in pinned["payees"].items():
        assert features["payees"][key] == row


def test_agents_can_load_it(features):
    """Round-trips through the same JSON the agents' JsonFeatureStore parses."""
    assert json.loads(dumps(features)) == features


def test_signals_reach_the_feature_store(features):
    payees = features["payees"]
    assert any("reported_by_users" in r["flags"] for r in payees.values())
    assert any("vpa_created_recently" in r["flags"] for r in payees.values())
    assert max(r["reported_links"] for r in payees.values()) >= 5  # mule rings share handsets
    busiest_non_merchant = max(r["fan_in_24h"] for r in payees.values() if not r["is_merchant"])
    assert busiest_non_merchant >= 10  # ring A's collector is live right now
    ordinary = [r for r in payees.values() if not r["flags"] and not r["is_merchant"]]
    assert len(ordinary) > 1_500  # most people are just people


def test_committed_features_json_is_up_to_date(features):
    """Fails if generator code changed without re-running `python -m generator --seed 42`."""
    committed = json.loads(DEFAULT_FEATURES.read_text(encoding="utf-8"))
    assert committed == features
