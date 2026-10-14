"""Build services/agents/data/mock/features.json from the dataset.

Definitions (the BigQuery views v_payer_features / v_payee_features compute the same, as of AS_OF):

payers, keyed by payer_id, over the payer's outgoing transactions in the 90-day window
  median_amount   exact median of amount (PERCENTILE_CONT 0.5)
  avg_daily_txn   count / 90, rounded to 3 decimals
  txn_count_1h    count with ts in (AS_OF - 1h, AS_OF]
  txn_count_24h   count with ts in (AS_OF - 24h, AS_OF]

payees, keyed by lower-case VPA, for every account that received at least one payment
  flags           "reported_by_users"    a payment into it was reported by the payer (labels)
                  "vpa_created_recently" account created within RECENT_VPA_DAYS of AS_OF
  reported_links  distinct OTHER accounts sharing a device_id or phone_id with the payee that
                  received at least one payment labelled is_scam
  fan_in_24h      distinct payers paying it with ts in (AS_OF - 24h, AS_OF]
  is_merchant     account_type = 'merchant'

The demo rows (payer_demo_001..004 and the six demo payees) are pinned: they come verbatim
from pinned_features.json and always win over generated rows.
"""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import pandas as pd

from . import config as C
from .pipeline import Dataset

PINNED_PATH = Path(__file__).with_name("pinned_features.json")
FLAG_ORDER = ("reported_by_users", "vpa_created_recently")

DEFAULTS = {
    "payer": {"median_amount": None, "avg_daily_txn": 2, "txn_count_1h": 0, "txn_count_24h": 0},
    "payee": {"flags": [], "reported_links": 0, "fan_in_24h": 0, "is_merchant": False},
}


def load_pinned() -> dict:
    return json.loads(PINNED_PATH.read_text(encoding="utf-8"))


def _in_window(tx: pd.DataFrame) -> pd.DataFrame:
    """Payments in [AS_OF - WINDOW_DAYS, AS_OF]: the same filter the BigQuery views apply."""
    as_of = pd.Timestamp(C.AS_OF)
    start = as_of - timedelta(days=C.WINDOW_DAYS)
    return tx[(tx["ts"] >= start) & (tx["ts"] <= as_of)]


def payer_features(ds: Dataset) -> dict[str, dict]:
    tx = _in_window(ds["transactions"])
    as_of = pd.Timestamp(C.AS_OF)
    in_1h = tx["ts"] > as_of - timedelta(hours=1)
    in_24h = tx["ts"] > as_of - timedelta(hours=24)
    grouped = tx.assign(in_1h=in_1h, in_24h=in_24h).groupby("payer_id", sort=True)
    agg = grouped.agg(
        median_amount=("amount", "median"),
        n=("amount", "size"),
        txn_count_1h=("in_1h", "sum"),
        txn_count_24h=("in_24h", "sum"),
    )
    return {
        payer_id: {
            "median_amount": round(float(r.median_amount), 2),
            "avg_daily_txn": round(r.n / C.WINDOW_DAYS, 3),
            "txn_count_1h": int(r.txn_count_1h),
            "txn_count_24h": int(r.txn_count_24h),
        }
        for payer_id, r in agg.iterrows()
    }


def payee_features(ds: Dataset) -> dict[str, dict]:
    tx, labels, accounts, devices = (
        _in_window(ds["transactions"]),
        ds["labels"],
        ds["accounts"],
        ds["devices"],
    )
    as_of = pd.Timestamp(C.AS_OF)
    lab = tx[["txn_id", "payee_account_id", "payer_id", "ts"]].merge(labels, on="txn_id")

    was_reported = lab["reported_by_user"] & (lab["reported_at"] <= as_of)
    reported = set(lab.loc[was_reported, "payee_account_id"])
    scam_labelled = set(lab.loc[lab["is_scam"], "payee_account_id"])
    recent_cutoff = as_of - timedelta(days=C.RECENT_VPA_DAYS)
    recent = set(accounts.loc[accounts["created_at"] >= recent_cutoff, "account_id"])
    fan_in = (
        tx[tx["ts"] > as_of - timedelta(hours=24)].groupby("payee_account_id")["payer_id"].nunique()
    )

    # Accounts linked through a shared handset (device_id) or SIM (phone_id).
    links: dict[str, set[str]] = {}
    for key in ("device_id", "phone_id"):
        for _, ids in devices.groupby(key)["account_id"]:
            members = sorted(set(ids))
            if len(members) < 2:
                continue
            for a in members:
                links.setdefault(a, set()).update(m for m in members if m != a)

    acct = accounts.set_index("account_id")
    out: dict[str, dict] = {}
    for account_id in sorted(tx["payee_account_id"].unique()):
        flags = []
        if account_id in reported:
            flags.append("reported_by_users")
        if account_id in recent:
            flags.append("vpa_created_recently")
        out[acct.at[account_id, "vpa"].lower()] = {
            "flags": flags,
            "reported_links": len(links.get(account_id, set()) & scam_labelled),
            "fan_in_24h": int(fan_in.get(account_id, 0)),
            "is_merchant": bool(acct.at[account_id, "account_type"] == "merchant"),
        }
    return dict(sorted(out.items()))


def build_features(ds: Dataset) -> dict:
    pinned = load_pinned()
    payers = dict(pinned["payers"])
    payees = dict(pinned["payees"])
    for key, row in payer_features(ds).items():
        payers.setdefault(key, row)
    for key, row in payee_features(ds).items():
        payees.setdefault(key, row)
    return {
        "_comment": (
            "Mock feature store for TRUSTSHIELD_MODE=mock. SYNTHETIC data, generated by data/ "
            f"(python -m generator --seed {ds.seed}). The demo rows (payer_demo_*, the six demo "
            "payees) are pinned from data/generator/pinned_features.json. Do not edit by hand."
        ),
        "schema_version": 1,
        "payers": payers,
        "payees": payees,
        "defaults": DEFAULTS,
    }


def dumps(features: dict) -> str:
    """Stable JSON with one payer / payee per line, so diffs stay readable."""

    def block(rows: dict) -> str:
        lines = [
            f"    {json.dumps(k)}: {json.dumps(v, ensure_ascii=False, allow_nan=False)}"
            for k, v in rows.items()
        ]
        return "{\n" + ",\n".join(lines) + "\n  }"

    return (
        "{\n"
        f'  "_comment": {json.dumps(features["_comment"], ensure_ascii=False)},\n'
        f'  "schema_version": {features["schema_version"]},\n'
        f'  "payers": {block(features["payers"])},\n'
        f'  "payees": {block(features["payees"])},\n'
        f'  "defaults": {json.dumps(features["defaults"])}\n'
        "}\n"
    )
