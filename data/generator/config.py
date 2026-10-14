"""Generator constants. Everything is relative to a fixed AS_OF so output never depends on the clock."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))

#: "Now" for the synthetic world: features (1h / 24h windows, recent VPAs) are computed here.
AS_OF = datetime(2026, 10, 13, 21, 0, tzinfo=IST)
WINDOW_DAYS = 90
WINDOW_START = AS_OF - timedelta(days=WINDOW_DAYS)

VPA_DOMAIN = "synthbank"

N_USERS = 2_000
N_TRANSACTIONS = 50_000
N_MERCHANTS = 50  # including the two pinned demo merchants

#: Scam archetypes, named like the agents' Scam Context patterns.
ARCHETYPES = ("urgency", "fake_kyc", "fake_refund", "receive_money_first", "qr_swap")

#: Feature thresholds (mirrored by the BigQuery feature views in data/bq/).
RECENT_VPA_DAYS = 7  # payee VPA created within this many days of AS_OF -> vpa_created_recently


@dataclass(frozen=True)
class ArchetypeSpec:
    victims: int  # number of victim payments (before velocity bursts)
    accounts: int  # scammer collector VPAs
    amount_range: tuple[int, int]
    device_changed_p: float
    burst_p: float  # chance the victim pays again within the hour
    channel: str


ARCHETYPE_SPECS: dict[str, ArchetypeSpec] = {
    "urgency": ArchetypeSpec(95, 6, (8_000, 95_000), 0.35, 0.25, "p2p"),
    "fake_kyc": ArchetypeSpec(90, 6, (999, 14_999), 0.25, 0.15, "p2p"),
    "fake_refund": ArchetypeSpec(85, 6, (1_500, 25_000), 0.10, 0.40, "p2p"),
    "receive_money_first": ArchetypeSpec(85, 6, (500, 12_000), 0.10, 0.20, "collect"),
    "qr_swap": ArchetypeSpec(80, 6, (150, 4_500), 0.0, 0.0, "qr"),
}


@dataclass(frozen=True)
class MuleRingSpec:
    ring_id: str
    scheme: str  # the archetype the ring cashes out for
    members: int
    victims: int
    active_days: tuple[int, int]  # (start, end) in days before AS_OF
    victims_last_24h: int
    amount_range: tuple[int, int]


MULE_RINGS = (
    # Ring A is live right now: many victims paying one collector VPA today.
    MuleRingSpec("ring_a", "urgency", 8, 60, (9, 0), 16, (5_000, 60_000)),
    # Ring B ran for a few weeks and was reported.
    MuleRingSpec("ring_b", "fake_refund", 7, 45, (55, 20), 0, (2_000, 20_000)),
)

#: Hard negatives: legitimate payments that look risky on one axis.
HARD_NEGATIVES = {
    "big_legit_rent": 0,  # derived: 3 monthly payments for every user with a landlord
    "big_legit_fees": 70,
    "big_legit_gift": 140,
    "big_legit_medical": 60,
    "new_genuine_payee": 450,
}
LANDLORD_SHARE = 0.18  # share of users who pay rent to a landlord they've paid for months

#: Reserved ids that generated data must never reuse (demo fixtures, tests, evals).
RESERVED_TXN_IDS = frozenset({"428913570012"})
DEMO_MERCHANTS = (
    # merchant_id, vpa, name, category, city
    ("MER-DEMO-0042", "mer.demo0042@synthbank", "Demo Electronics", "electronics", "Bengaluru"),
    ("MER-DEMO-0007", "chai.ramesh@synthbank", "Ramesh Chai Stall", "cafe", "Bengaluru"),
)

CITIES = (
    # name, lat, lon, weight
    ("Bengaluru", 12.9716, 77.5946, 14),
    ("Mumbai", 19.0760, 72.8777, 14),
    ("Delhi", 28.6139, 77.2090, 14),
    ("Hyderabad", 17.3850, 78.4867, 10),
    ("Chennai", 13.0827, 80.2707, 9),
    ("Pune", 18.5204, 73.8567, 8),
    ("Kolkata", 22.5726, 88.3639, 8),
    ("Ahmedabad", 23.0225, 72.5714, 6),
    ("Jaipur", 26.9124, 75.7873, 5),
    ("Lucknow", 26.8467, 80.9462, 4),
    ("Indore", 22.7196, 75.8577, 4),
    ("Kochi", 9.9312, 76.2673, 4),
)

MERCHANT_CATEGORIES = (
    # category, name suffix, share of merchants, typical amount multiplier
    ("kirana", "General Store", 8, 0.6),
    ("restaurant", "Family Restaurant", 6, 1.2),
    ("cafe", "Cafe", 4, 0.4),
    ("pharmacy", "Medicals", 5, 0.8),
    ("fuel", "Fuel Station", 4, 1.5),
    ("electronics", "Electronics", 3, 3.0),
    ("clothing", "Fashions", 4, 2.0),
    ("salon", "Salon", 3, 0.9),
    ("school", "Public School", 3, 1.0),
    ("hospital", "Hospital", 2, 1.0),
    ("telecom", "Mobile Recharge", 3, 0.5),
    ("transport", "Travels", 3, 1.4),
)
