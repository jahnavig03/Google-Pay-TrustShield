"""Everyday payments and the hard negatives: legitimate payments that look risky on one axis."""

from __future__ import annotations

from datetime import datetime, timedelta

from . import config as C
from .messages import NORMAL_NOTES, legit_message
from .world import Intent, UserProfile, World

_CATEGORY_MULT = {c[0]: c[3] for c in C.MERCHANT_CATEGORIES}


def _rent_days(world: World) -> list[datetime]:
    """The 1st–6th of every month that falls inside the window."""
    days, month = [], C.WINDOW_START.replace(day=1, hour=10, minute=0, second=0)
    while month <= C.AS_OF:
        day = month + timedelta(days=world.rng.randint(0, 5))
        if C.WINDOW_START <= day <= C.AS_OF:
            days.append(day)
        month = (month + timedelta(days=32)).replace(day=1)
    return days


def _merchants_in(world: World, *categories: str):
    return [m for m in world.merchants if m.category in categories]


def build_hard_negatives(world: World) -> None:
    rng = world.rng
    rent_days = _rent_days(world)

    def add(profile: UserProfile, ts, payee_vpa, amount, channel, kind, message_p, added=None):
        world.add(
            Intent(
                ts=ts,
                payer_id=profile.account.account_id,
                payee_vpa=payee_vpa,
                amount=amount,
                channel=channel,
                message_context=legit_message(rng, kind, amount)
                if rng.random() < message_p
                else None,
                added_minutes_before=added,
                is_hard_negative=True,
                hard_negative_type=kind,
            )
        )

    # Rent: big (many times the payer's median) but to a landlord paid every month.
    for profile in world.users:
        if profile.landlord is None:
            continue
        rent = float(round(min(max(profile.amount_scale * rng.uniform(8, 25), 6_000), 45_000), -2))
        for day in rent_days:
            ts = world.time_of_day(day)
            if ts <= C.AS_OF:
                add(profile, ts, profile.landlord, rent, "p2p", "big_legit_rent", 0.3)

    # School / college fees: large, to a school the family has paid before.
    schools = _merchants_in(world, "school")
    for _ in range(C.HARD_NEGATIVES["big_legit_fees"]):
        profile, school = rng.choice(world.users), rng.choice(schools)
        world.register_beneficiary(
            profile.account.account_id,
            school.vpa,
            C.WINDOW_START - timedelta(days=rng.randint(120, 900)),
        )
        amount = float(round(rng.uniform(8_000, 60_000), -2))
        add(profile, world.random_ts(), school.vpa, amount, "p2m", "big_legit_fees", 0.5)

    # Gifts (birthdays, weddings): large, to an old contact.
    for _ in range(C.HARD_NEGATIVES["big_legit_gift"]):
        profile = rng.choice(world.users)
        amount = float(rng.choice([5_001, 5_100, 11_000, 11_001, 21_000, 21_001, 31_000, 51_000]))
        add(
            profile,
            world.random_ts(),
            rng.choice(profile.contacts),
            amount,
            "p2p",
            "big_legit_gift",
            0.4,
        )

    # Medical: large, often to a hospital the payer has never paid (a new payee with a big amount).
    medical = _merchants_in(world, "hospital", "pharmacy")
    for _ in range(C.HARD_NEGATIVES["big_legit_medical"]):
        profile, payee = rng.choice(world.users), rng.choice(medical)
        amount = float(round(rng.uniform(3_000, 40_000), -2))
        add(
            profile,
            world.random_ts(),
            payee.vpa,
            amount,
            "p2m",
            "big_legit_medical",
            0.5,
            added=rng.uniform(5, 90),
        )

    # New but genuine payees: a plumber, a tutor, a friend-of-a-friend splitting a bill.
    user_vpas = [u.account.vpa for u in world.users]
    for _ in range(C.HARD_NEGATIVES["new_genuine_payee"]):
        profile = rng.choice(world.users)
        known = set(profile.contacts) | set(profile.merchants) | {profile.account.vpa}
        if rng.random() < 0.6:
            payee = rng.choice([v for v in rng.sample(user_vpas, 8) if v not in known] or user_vpas)
            channel = "p2p"
        else:
            payee = rng.choice([m.vpa for m in world.merchants if m.vpa not in known])
            channel = "p2m"
        amount = world.lognormal_amount(profile.amount_scale * 1.2, 0.7, lo=50, hi=8_000)
        add(
            profile,
            world.random_ts(),
            payee,
            amount,
            channel,
            "new_genuine_payee",
            0.35,
            added=rng.uniform(1, 30),
        )


def build_normal(world: World, count: int) -> None:
    """``count`` everyday payments, spread over users by a heavy-tailed activity weight."""
    rng = world.rng
    weights = [u.activity_weight for u in world.users]
    merchants_by_vpa = {m.vpa: m for m in world.merchants}
    for profile in rng.choices(world.users, weights, k=count):
        ts = world.random_ts()
        added = None
        if rng.random() < 0.55:
            if rng.random() < 0.03:  # trying a new shop
                payee = rng.choice(world.merchants)
                added = rng.uniform(0.2, 3)
            else:
                payee = merchants_by_vpa[rng.choice(profile.merchants)]
            mult = _CATEGORY_MULT.get(payee.category or "", 1.0)
            amount = world.lognormal_amount(profile.amount_scale * mult * 0.7, 0.6)
            channel, note, payee_vpa = rng.choice(("p2m", "qr")), None, payee.vpa
        else:
            payee_vpa = rng.choice(profile.contacts)
            amount = world.lognormal_amount(profile.amount_scale * 1.3, 0.8)
            channel = "p2p"
            note = rng.choice(NORMAL_NOTES) if rng.random() < 0.15 else None
        world.add(
            Intent(
                ts=ts,
                payer_id=profile.account.account_id,
                payee_vpa=payee_vpa,
                amount=amount,
                channel=channel,
                message_context=note,
                added_minutes_before=added,
            )
        )
