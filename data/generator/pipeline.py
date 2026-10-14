"""generate(seed) -> the full synthetic dataset as DataFrames."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

import pandas as pd

from . import config as C
from .activity import build_hard_negatives, build_normal
from .scams import build_archetypes, build_mule_rings
from .world import World, build_population

TABLES = (
    "accounts",
    "devices",
    "transactions",
    "beneficiaries",
    "labels",
    "merchants",
    "merchant_ledger",
)

#: Share of scam victims who report it, and how long they take (mean, hours).
REPORT_P = 0.65
REPORT_DELAY_MEAN_H = 20


@dataclass
class Dataset:
    seed: int
    tables: dict[str, pd.DataFrame]

    def __getitem__(self, name: str) -> pd.DataFrame:
        return self.tables[name]


def _finalize(world: World) -> tuple[list[dict], list[dict]]:
    """Replay intents in time order: assign txn ids, device / location / beneficiary fields."""
    rng = world.rng
    known_devices: dict[str, set[str]] = {}
    first_device: dict[str, str] = {}
    for row in world.device_rows:
        if row["first_seen"] < C.WINDOW_START:
            known_devices.setdefault(row["account_id"], set()).add(row["device_id"])
        first_device.setdefault(row["account_id"], row["device_id"])

    txns, labels = [], []
    order = sorted(world.intents, key=lambda i: (i.ts, i.payer_id, i.payee_vpa, i.amount))
    for it in order:
        payer = world.by_id[it.payer_id]
        payee = world.by_vpa[it.payee_vpa]
        profile = world.profiles.get(it.payer_id)
        device = it.device_id or (
            world.device_at(profile, it.ts) if profile else first_device[it.payer_id]
        )
        city = it.city or (world.city_at(profile, it.ts) if profile else payer.home_city)
        seen = known_devices.setdefault(it.payer_id, set())
        device_changed = device not in seen
        seen.add(device)

        key = (it.payer_id, it.payee_vpa)
        if key not in world.beneficiary_added:
            minutes = it.added_minutes_before
            if minutes is None:
                minutes = rng.uniform(0.5, 30)
            world.beneficiary_added[key] = it.ts - timedelta(minutes=minutes)
        age = int((it.ts - world.beneficiary_added[key]).total_seconds() // 60)

        lat, lon = world.city_geo[city]
        txn_id = world.txn_id()
        txns.append(
            {
                "txn_id": txn_id,
                "ts": it.ts,
                "payer_id": it.payer_id,
                "payer_vpa": payer.vpa,
                "payee_vpa": it.payee_vpa,
                "payee_account_id": payee.account_id,
                "amount": round(float(it.amount), 2),
                "currency": "INR",
                "channel": it.channel,
                "device_id": device,
                "device_changed": device_changed,
                "city": city,
                "lat": round(lat + rng.gauss(0, 0.03), 5),
                "lon": round(lon + rng.gauss(0, 0.03), 5),
                "location_changed": city != payer.home_city,
                "beneficiary_age_minutes": max(age, 0),
                "message_context": it.message_context,
                "status": "success",
            }
        )
        reported_at = None
        if it.is_scam and it.scam_type != "mule_layering" and rng.random() < REPORT_P:
            when = it.ts + timedelta(hours=rng.expovariate(1 / REPORT_DELAY_MEAN_H))
            reported_at = when if when <= C.AS_OF else None
        labels.append(
            {
                "txn_id": txn_id,
                "is_scam": it.is_scam,
                "scam_type": it.scam_type,
                "ring_id": it.ring_id,
                "is_hard_negative": it.is_hard_negative,
                "hard_negative_type": it.hard_negative_type,
                "intended_payee_vpa": it.intended_payee_vpa,
                "reported_by_user": reported_at is not None,
                "reported_at": reported_at,
            }
        )
    return txns, labels


def _ledger(world: World, txns: pd.DataFrame) -> list[dict]:
    """Merchant ledger: every credit to the 50 merchants, settlement status, refunds and abuse."""
    rng = world.rng
    merchants = {m.vpa: m for m in world.merchants}
    credits = txns[txns["payee_vpa"].isin(list(merchants))]
    rows: list[dict] = []
    for t in credits.itertuples(index=False):
        recent = t.ts > C.AS_OF - timedelta(minutes=20)
        pending = recent or rng.random() < 0.015
        rows.append(
            {
                "merchant_id": merchants[t.payee_vpa].merchant_id,
                "merchant_vpa": t.payee_vpa,
                "entry_type": "credit",
                "txn_id": t.txn_id,
                "amount": t.amount,
                "counterparty_vpa": t.payer_vpa,
                "initiated_at": t.ts,
                "settled_at": None if pending else t.ts + timedelta(seconds=rng.randint(5, 180)),
                "status": "pending" if pending else "settled",
                "refund_of_txn_id": None,
                "refund_abuse_pattern": "none",
            }
        )
    settled = [r for r in rows if r["status"] == "settled"]
    user_vpas = [u.account.vpa for u in world.users]

    def refund(orig: dict, amount: float, to_vpa: str, pattern: str, days: tuple[float, float]):
        ts = orig["initiated_at"] + timedelta(days=rng.uniform(*days))
        if ts > C.AS_OF:
            return
        rows.append(
            {
                "merchant_id": orig["merchant_id"],
                "merchant_vpa": orig["merchant_vpa"],
                "entry_type": "refund",
                "txn_id": world.txn_id(),
                "amount": round(float(amount), 2),
                "counterparty_vpa": to_vpa,
                "initiated_at": ts,
                "settled_at": ts + timedelta(seconds=rng.randint(30, 600)),
                "status": "settled",
                "refund_of_txn_id": orig["txn_id"],
                "refund_abuse_pattern": pattern,
            }
        )

    for orig in rng.sample(settled, int(len(settled) * 0.025)):  # ordinary returns
        share = 1.0 if rng.random() < 0.7 else rng.uniform(0.2, 0.9)
        refund(orig, round(orig["amount"] * share), orig["counterparty_vpa"], "none", (0.5, 10))
    # Serial refunders: a few payers claim refunds at shop after shop.
    by_payer: dict[str, list[dict]] = {}
    for r in settled:
        by_payer.setdefault(r["counterparty_vpa"], []).append(r)
    heavy = sorted(v for v, rs in by_payer.items() if len(rs) >= 8)
    for vpa in rng.sample(heavy, min(10, len(heavy))):
        for orig in rng.sample(by_payer[vpa], rng.randint(5, min(10, len(by_payer[vpa])))):
            refund(orig, orig["amount"], vpa, "serial_refunder", (0.2, 3))
    for orig in rng.sample(settled, 15):
        refund(
            orig,
            round(orig["amount"] * rng.uniform(1.15, 2.0)),
            orig["counterparty_vpa"],
            "refund_exceeds_original",
            (0.2, 5),
        )
    for orig in rng.sample(settled, 15):
        other = rng.choice([v for v in rng.sample(user_vpas, 3) if v != orig["counterparty_vpa"]])
        refund(orig, orig["amount"], other, "refund_to_different_vpa", (0.2, 5))
    for orig in rng.sample(settled, 10):
        for _ in range(2):
            refund(orig, orig["amount"], orig["counterparty_vpa"], "duplicate_refund", (0.1, 2))

    rows.sort(key=lambda r: (r["initiated_at"], r["txn_id"]))
    for i, r in enumerate(rows, start=1):
        r["ledger_entry_id"] = f"LE{i:08d}"
    return rows


def _utc(df: pd.DataFrame, *cols: str) -> pd.DataFrame:
    """Timestamps as UTC microseconds (what BigQuery TIMESTAMP loads from Parquet)."""
    for col in cols:
        df[col] = pd.to_datetime(df[col], utc=True).astype("datetime64[us, UTC]")
    return df


def generate(seed: int = 42) -> Dataset:
    world = World(seed)
    build_population(world)
    build_archetypes(world)
    build_mule_rings(world)
    build_hard_negatives(world)
    remaining = C.N_TRANSACTIONS - len(world.intents)
    if remaining <= 0:
        raise ValueError("special transactions exceed N_TRANSACTIONS")
    build_normal(world, remaining)

    txn_rows, label_rows = _finalize(world)
    txns = _utc(pd.DataFrame(txn_rows), "ts")
    labels = _utc(pd.DataFrame(label_rows), "reported_at")
    ledger_cols = [
        "ledger_entry_id",
        "merchant_id",
        "merchant_vpa",
        "entry_type",
        "txn_id",
        "amount",
        "counterparty_vpa",
        "initiated_at",
        "settled_at",
        "status",
        "refund_of_txn_id",
        "refund_abuse_pattern",
    ]
    ledger = _utc(pd.DataFrame(_ledger(world, txns))[ledger_cols], "initiated_at", "settled_at")

    accounts = _utc(
        pd.DataFrame(
            [
                {
                    "account_id": a.account_id,
                    "vpa": a.vpa,
                    "account_type": a.account_type,
                    "display_name": a.display_name,
                    "home_city": a.home_city,
                    "created_at": a.created_at,
                    "merchant_id": a.merchant_id,
                    "ring_id": a.ring_id,
                }
                for a in world.accounts
            ]
        ),
        "created_at",
    )
    devices = _utc(pd.DataFrame(world.device_rows), "first_seen")
    beneficiaries = _utc(
        pd.DataFrame(
            [
                {
                    "payer_id": payer,
                    "payee_vpa": vpa,
                    "payee_account_id": world.by_vpa[vpa].account_id,
                    "added_at": added,
                }
                for (payer, vpa), added in sorted(world.beneficiary_added.items())
            ]
        ),
        "added_at",
    )
    merchants = pd.DataFrame(
        [
            {
                "merchant_id": m.merchant_id,
                "account_id": m.account_id,
                "merchant_vpa": m.vpa,
                "name": m.display_name,
                "category": m.category,
                "city": m.home_city,
            }
            for m in world.merchants
        ]
    )
    tables = {
        "accounts": accounts,
        "devices": devices,
        "transactions": txns,
        "beneficiaries": beneficiaries,
        "labels": labels,
        "merchants": merchants,
        "merchant_ledger": ledger,
    }
    return Dataset(seed, tables)
