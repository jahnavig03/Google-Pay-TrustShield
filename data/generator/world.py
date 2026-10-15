"""The synthetic world: accounts, devices, and the shared state every activity module writes into.

Payments are first recorded as *intents* in any order. ``finalize`` then replays them in time
order to derive what depends on history: device_changed, beneficiary age and new-payee rows.
"""

from __future__ import annotations

import math
import random
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from faker import Faker

from . import config as C

# Activity by hour of day (IST): quiet at night, peaks around lunch and evening.
_HOUR_WEIGHTS = (1, 0.5, 0.3, 0.3, 0.4, 0.8, 2, 4, 6, 7, 7, 8, 9, 8, 7, 7, 7, 8, 9, 10, 10, 8, 5, 2)


def slug(text: str) -> str:
    """Lowercase ASCII letters only (VPA-safe)."""
    return re.sub(r"[^a-z]", "", text.lower()) or "x"


@dataclass
class Account:
    account_id: str
    vpa: str
    account_type: str  # user | merchant | scammer | mule
    display_name: str
    home_city: str
    created_at: datetime
    merchant_id: str | None = None
    category: str | None = None
    archetype: str | None = None  # scammer accounts: which scheme they run
    ring_id: str | None = None  # mule accounts
    pinned: bool = False  # demo entity whose features.json row is pinned


@dataclass
class UserProfile:
    account: Account
    amount_scale: float  # typical payment size in ₹
    activity_weight: float  # relative share of normal transactions
    devices: list[tuple[datetime, str]]  # (from, device_id), time-ordered
    contacts: list[str] = field(default_factory=list)  # VPAs
    merchants: list[str] = field(default_factory=list)  # VPAs
    landlord: str | None = None
    trips: list[tuple[datetime, datetime, str]] = field(default_factory=list)


@dataclass
class Intent:
    """One payment before history-dependent fields are derived."""

    ts: datetime
    payer_id: str
    payee_vpa: str
    amount: float
    channel: str  # p2p | p2m | qr | collect
    message_context: str | None = None
    device_id: str | None = None  # override (e.g. a scam session on an unknown device)
    city: str | None = None  # override; default = payer's location at ts
    added_minutes_before: float | None = None  # new payee added this long before paying
    # labels
    is_scam: bool = False
    scam_type: str = "none"
    ring_id: str | None = None
    is_hard_negative: bool = False
    hard_negative_type: str = "none"
    intended_payee_vpa: str | None = None  # qr_swap: the merchant the payer meant to pay


class World:
    def __init__(self, seed: int):
        self.seed = seed
        self.rng = random.Random(seed)
        self.fake = Faker("en_IN")
        self.fake.seed_instance(seed)
        self.accounts: list[Account] = []
        self.by_vpa: dict[str, Account] = {}
        self.by_id: dict[str, Account] = {}
        self.users: list[UserProfile] = []
        self.profiles: dict[str, UserProfile] = {}
        self.merchants: list[Account] = []
        self.device_rows: list[dict] = []
        self.intents: list[Intent] = []
        self.beneficiary_added: dict[tuple[str, str], datetime] = {}
        self._used_ids: set[str] = set(C.RESERVED_TXN_IDS)
        self._city_names = [c[0] for c in C.CITIES]
        self._city_weights = [c[3] for c in C.CITIES]
        self.city_geo = {c[0]: (c[1], c[2]) for c in C.CITIES}

    # ------------------------------------------------------------------ ids and sampling
    def unique_id(self, prefix: str, digits: int) -> str:
        while True:
            value = f"{prefix}{self.rng.randrange(10 ** (digits - 1), 10**digits)}"
            if value not in self._used_ids:
                self._used_ids.add(value)
                return value

    def txn_id(self) -> str:
        """12-digit UPI reference number (UTR-like)."""
        return self.unique_id("", 12)

    def device_id(self) -> str:
        return "dev_" + self.unique_id("", 10)

    def phone_id(self) -> str:
        """Opaque phone identifier. No realistic phone numbers in synthetic data."""
        return "ph_" + self.unique_id("", 9)

    def random_city(self) -> str:
        return self.rng.choices(self._city_names, self._city_weights)[0]

    def time_of_day(self, day: datetime) -> datetime:
        hour = self.rng.choices(range(24), _HOUR_WEIGHTS)[0]
        return day.replace(hour=hour, minute=self.rng.randrange(60), second=self.rng.randrange(60))

    def random_ts(self, start: datetime | None = None, end: datetime | None = None) -> datetime:
        """A plausible payment time in [start, end] (default: the whole window)."""
        start, end = start or C.WINDOW_START, end or C.AS_OF
        for _ in range(20):
            span_days = max((end - start).total_seconds() / 86400, 1 / 24)
            day = start + timedelta(days=self.rng.uniform(0, span_days))
            ts = self.time_of_day(day)
            if start <= ts <= end:
                return ts
        return start + (end - start) * self.rng.random()

    def lognormal_amount(self, median: float, sigma: float, lo: float = 10, hi: float = 200_000):
        value = median * math.exp(self.rng.gauss(0, sigma))
        return float(round(min(max(value, lo), hi)))

    # ------------------------------------------------------------------ accounts and devices
    def add_account(self, account: Account) -> Account:
        if account.vpa in self.by_vpa or account.account_id in self.by_id:
            raise ValueError(f"duplicate account {account.account_id} / {account.vpa}")
        self.accounts.append(account)
        self.by_vpa[account.vpa] = account
        self.by_id[account.account_id] = account
        return account

    def add_device(
        self,
        account_id: str,
        device_id: str,
        phone_id: str,
        first_seen: datetime,
        is_primary: bool,
    ) -> None:
        self.device_rows.append(
            {
                "account_id": account_id,
                "device_id": device_id,
                "phone_id": phone_id,
                "first_seen": first_seen,
                "is_primary": is_primary,
            }
        )

    def person_vpa(self, first: str, last: str, n: int) -> str:
        return f"{slug(first)}.{slug(last)}.{n:05d}@{C.VPA_DOMAIN}"

    def register_beneficiary(self, payer_id: str, payee_vpa: str, added_at: datetime) -> None:
        self.beneficiary_added.setdefault((payer_id, payee_vpa), added_at)

    def add(self, intent: Intent) -> Intent:
        if intent.ts > C.AS_OF:
            raise ValueError("payment after AS_OF")
        self.intents.append(intent)
        return intent

    # ------------------------------------------------------------------ payer state at time t
    def device_at(self, profile: UserProfile, ts: datetime) -> str:
        current = profile.devices[0][1]
        for start, device in profile.devices:
            if start <= ts:
                current = device
        return current

    def city_at(self, profile: UserProfile, ts: datetime) -> str:
        for start, end, city in profile.trips:
            if start <= ts <= end:
                return city
        return profile.account.home_city


def build_population(world: World) -> None:
    """2,000 users with devices, contacts, regular merchants, landlords and trips; 50 merchants."""
    rng, fake = world.rng, world.fake

    # Merchants first so users can pick regular shops.
    n_generated = C.N_MERCHANTS - len(C.DEMO_MERCHANTS)
    cats, cat_weights = zip(*((c[0], c[2]) for c in C.MERCHANT_CATEGORIES), strict=True)
    suffix = {c[0]: c[1] for c in C.MERCHANT_CATEGORIES}
    for i in range(1, n_generated + 1):
        category = cats[i % len(cats)] if i <= len(cats) else rng.choices(cats, cat_weights)[0]
        owner = fake.last_name()
        name = f"{owner} {suffix[category]}"
        acct = Account(
            account_id=f"acct_m{i:04d}",
            vpa=f"mer.{slug(owner)}{category[:4]}.{i:04d}@{C.VPA_DOMAIN}",
            account_type="merchant",
            display_name=name,
            home_city=world.random_city(),
            created_at=C.WINDOW_START - timedelta(days=rng.randint(200, 2000)),
            merchant_id=f"MER-{i:04d}",
            category=category,
        )
        world.merchants.append(world.add_account(acct))
    for merchant_id, vpa, name, category, city in C.DEMO_MERCHANTS:
        acct = Account(
            account_id="acct_" + merchant_id.lower().replace("-", "_"),
            vpa=vpa,
            account_type="merchant",
            display_name=name,
            home_city=city,
            created_at=C.WINDOW_START - timedelta(days=900),
            merchant_id=merchant_id,
            category=category,
            pinned=True,
        )
        world.merchants.append(world.add_account(acct))
    for m in world.merchants:
        world.add_device(m.account_id, world.device_id(), world.phone_id(), m.created_at, True)

    # Users.
    for i in range(1, C.N_USERS + 1):
        first, last = fake.first_name(), fake.last_name()
        acct = world.add_account(
            Account(
                account_id=f"user_{i:05d}",
                vpa=world.person_vpa(first, last, i),
                account_type="user",
                display_name=f"{first} {last}",
                home_city=world.random_city(),
                created_at=C.WINDOW_START - timedelta(days=rng.randint(30, 2500)),
            )
        )
        primary = world.device_id()
        phone = world.phone_id()
        device_from = acct.created_at
        devices = [(device_from, primary)]
        world.add_device(acct.account_id, primary, phone, device_from, True)
        if rng.random() < 0.22:  # bought a new phone during the window
            switch = world.random_ts()
            new_device = world.device_id()
            devices.append((switch, new_device))
            world.add_device(acct.account_id, new_device, phone, switch, True)
        profile = UserProfile(
            account=acct,
            amount_scale=min(max(600 * math.exp(rng.gauss(0, 0.75)), 80), 9_000),
            activity_weight=math.exp(rng.gauss(0, 1.0)),
            devices=devices,
        )
        if rng.random() < 0.12:  # one trip out of town
            start = world.random_ts(end=C.AS_OF - timedelta(days=3))
            others = [c for c in world._city_names if c != acct.home_city]
            profile.trips.append(
                (start, start + timedelta(days=rng.randint(2, 6)), rng.choice(others))
            )
        world.users.append(profile)
        world.profiles[acct.account_id] = profile

    # Social graph and regular merchants (all added well before the window).
    user_vpas = [u.account.vpa for u in world.users]
    for profile in world.users:
        me = profile.account
        contacts = rng.sample(user_vpas, rng.randint(3, 12))
        profile.contacts = [v for v in contacts if v != me.vpa]
        local = [m for m in world.merchants if m.home_city == me.home_city]
        pool = local + rng.sample(world.merchants, 4)
        picks = rng.sample(pool, min(len(pool), rng.randint(3, 8)))
        profile.merchants = sorted({m.vpa for m in picks})
        for vpa in profile.contacts + profile.merchants:
            world.register_beneficiary(
                me.account_id, vpa, C.WINDOW_START - timedelta(days=rng.randint(5, 700))
            )
        if rng.random() < C.LANDLORD_SHARE:
            landlord = rng.choice(user_vpas)
            if landlord != me.vpa:
                profile.landlord = landlord
                world.register_beneficiary(
                    me.account_id, landlord, C.WINDOW_START - timedelta(days=rng.randint(60, 900))
                )
