"""Shape and content of the synthetic dataset."""

import re

import pandas as pd

from generator import config as C
from generator.pipeline import TABLES


def test_sizes(ds):
    assert set(ds.tables) == set(TABLES)
    assert len(ds["transactions"]) == C.N_TRANSACTIONS
    assert (ds["accounts"]["account_type"] == "user").sum() == C.N_USERS
    assert len(ds["merchants"]) == C.N_MERCHANTS
    assert len(ds["labels"]) == len(ds["transactions"])


def test_ids_are_unique(ds):
    assert ds["transactions"]["txn_id"].is_unique
    assert ds["accounts"]["account_id"].is_unique
    assert ds["accounts"]["vpa"].is_unique
    assert ds["merchant_ledger"]["ledger_entry_id"].is_unique
    assert ds["merchant_ledger"]["txn_id"].is_unique


def test_everything_happens_inside_the_90_day_window(ds):
    ts = ds["transactions"]["ts"]
    assert ts.min() >= pd.Timestamp(C.WINDOW_START) and ts.max() <= pd.Timestamp(C.AS_OF)


def test_synthetic_identities_only(ds):
    vpas = ds["accounts"]["vpa"]
    assert vpas.str.endswith("@synthbank").all()
    assert vpas.str.fullmatch(r"[a-z0-9.]+@synthbank").all()
    # No phone numbers anywhere: phones are opaque ids.
    assert ds["devices"]["phone_id"].str.fullmatch(r"ph_\d{9}").all()


def test_generated_vpas_never_collide_with_hand_written_test_vpas(ds):
    """Tests and evals use hand-written VPAs without digits (friend.regular@synthbank, ...) that
    must fall through to features.json defaults. Every generated, non-pinned VPA carries digits."""
    pinned = {vpa for _, vpa, *_ in C.DEMO_MERCHANTS}
    generated = [v for v in ds["accounts"]["vpa"] if v not in pinned]
    assert all(re.search(r"\d", v) for v in generated)


def test_five_archetypes_and_two_mule_rings_are_labelled(ds):
    labels = ds["labels"]
    scams = labels[labels["is_scam"]]
    assert set(C.ARCHETYPES) <= set(scams["scam_type"])
    for archetype in C.ARCHETYPES:
        assert (scams["scam_type"] == archetype).sum() >= 50
    assert set(scams["ring_id"].dropna()) == {"ring_a", "ring_b"}
    assert (labels["scam_type"] == "none").sum() == (~labels["is_scam"]).sum()
    assert not (labels["is_scam"] & labels["is_hard_negative"]).any()


def test_mule_rings_share_devices_and_have_many_victims(ds):
    accounts, devices, tx = ds["accounts"], ds["devices"], ds["transactions"]
    for ring in C.MULE_RINGS:
        members = accounts.loc[accounts["ring_id"] == ring.ring_id, "account_id"]
        ring_devices = devices[devices["account_id"].isin(members)]
        assert ring_devices["device_id"].nunique() < len(members)  # handsets are shared
        users = set(accounts.loc[accounts["account_type"] == "user", "account_id"])
        into_ring = tx[tx["payee_account_id"].isin(members) & tx["payer_id"].isin(users)]
        assert into_ring["payer_id"].nunique() >= ring.victims * 0.9


def test_scam_payments_look_like_scams(ds):
    m = ds["transactions"].merge(ds["labels"], on="txn_id")
    victim = m[m["is_scam"] & (m["scam_type"] != "mule_layering")]
    assert (victim["beneficiary_age_minutes"] < 30).mean() > 0.8
    assert victim["message_context"].notna().all()
    assert (m.loc[m["scam_type"] == "receive_money_first", "channel"] == "collect").all()
    qr = m[m["scam_type"] == "qr_swap"]
    assert (qr["channel"] == "qr").all() and qr["intended_payee_vpa"].notna().all()


def test_hard_negatives_are_risky_looking_but_legitimate(ds):
    m = ds["transactions"].merge(ds["labels"], on="txn_id")
    hn = m[m["is_hard_negative"]]
    kinds = set(hn["hard_negative_type"])
    assert {
        "big_legit_rent",
        "big_legit_fees",
        "big_legit_gift",
        "big_legit_medical",
        "new_genuine_payee",
    } <= kinds
    rent = hn[hn["hard_negative_type"] == "big_legit_rent"]
    assert rent["amount"].min() >= 6_000 and (rent["beneficiary_age_minutes"] > 60 * 24 * 30).all()
    new = hn[hn["hard_negative_type"] == "new_genuine_payee"]
    assert (new["beneficiary_age_minutes"] < 60).mean() > 0.9


def test_merchant_ledger(ds):
    ledger, merchants = ds["merchant_ledger"], ds["merchants"]
    assert set(ledger["merchant_id"]) <= set(merchants["merchant_id"])
    assert {"settled", "pending"} == set(ledger["status"])
    assert ledger.loc[ledger["status"] == "pending", "settled_at"].isna().all()
    assert ledger.loc[ledger["status"] == "settled", "settled_at"].notna().all()
    refunds = ledger[ledger["entry_type"] == "refund"]
    assert refunds["refund_of_txn_id"].isin(ledger["txn_id"]).all()
    assert {
        "serial_refunder",
        "refund_exceeds_original",
        "refund_to_different_vpa",
        "duplicate_refund",
    } <= set(refunds["refund_abuse_pattern"])
    # Every credit in the ledger is a real payment to that merchant.
    credits = ledger[ledger["entry_type"] == "credit"]
    assert credits["txn_id"].isin(ds["transactions"]["txn_id"]).all()


def test_demo3_transaction_is_not_in_the_ledger(ds):
    """Demo 3: the fake ₹12,000 screenshot's transaction id must never settle."""
    ledger = ds["merchant_ledger"]
    assert "MER-DEMO-0042" in set(ledger["merchant_id"])
    assert not C.RESERVED_TXN_IDS & set(ledger["txn_id"])
    assert not C.RESERVED_TXN_IDS & set(ds["transactions"]["txn_id"])
