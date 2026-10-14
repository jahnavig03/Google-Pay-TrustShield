"""Labelled scam payments: 5 archetypes run from scammer VPAs, and 2 mule rings."""

from __future__ import annotations

import math
from datetime import timedelta

from . import config as C
from .messages import scam_message
from .world import Account, Intent, World, slug

_SCAM_VPA_STEMS = {
    "urgency": ("secure.account.desk", "bank.safety.cell", "acct.protect.team"),
    "fake_kyc": ("kyc.update.centre", "ekyc.verify.desk", "kyc.renewal.help"),
    "fake_refund": ("refund.care.team", "order.refund.help", "return.process.desk"),
    "receive_money_first": ("cashback.rewards", "prize.claim.cell", "lucky.draw.office"),
}


#: Shops that take payment from a printed QR at the counter (where a sticker can be swapped).
_QR_SHOPS = {"kirana", "cafe", "restaurant", "fuel", "pharmacy", "salon"}


def _scammy_amount(world: World, lo: int, hi: int) -> float:
    """Log-uniform in [lo, hi]; scammers like round or x,999 figures."""
    value = math.exp(world.rng.uniform(math.log(lo), math.log(hi)))
    roll = world.rng.random()
    if roll < 0.3:
        return float(max(lo, int(value / 1000) * 1000 + 999 if value >= 1000 else 499))
    if roll < 0.6:
        return float(max(lo, round(value, -3) if value >= 1000 else round(value, -2)))
    return float(round(value))


def _scam_session_device(world: World, victim_id: str, ts) -> str:
    """A payment from a device the victim never used before (screen-share / remote-access app)."""
    device = world.device_id()
    phone = next(r["phone_id"] for r in world.device_rows if r["account_id"] == victim_id)
    world.add_device(victim_id, device, phone, ts, False)
    return device


def _operator_accounts(world: World, archetype: str) -> list[tuple[Account, tuple]]:
    """Scammer VPAs for one archetype, each with its own active window (start, end)."""
    spec = C.ARCHETYPE_SPECS[archetype]
    rng = world.rng
    # One operator runs most VPAs from a shared pool of 2 phones/devices; the rest are standalone.
    pool = [(world.device_id(), world.phone_id()) for _ in range(2)]
    out = []
    for k in range(spec.accounts):
        if k < 2:  # new VPAs, active right now
            start = C.AS_OF - timedelta(days=rng.uniform(1, 5))
            end = C.AS_OF
        else:
            start = C.AS_OF - timedelta(days=rng.uniform(15, 85))
            end = min(start + timedelta(days=rng.uniform(4, 18)), C.AS_OF)
        created = start - timedelta(hours=rng.uniform(1, 40))
        n = len(world.accounts) + 1
        if archetype == "qr_swap":
            shops = [m for m in world.merchants if not m.pinned and m.category in _QR_SHOPS]
            target = rng.choice(shops)
            vpa = f"{slug(target.display_name)}.pay.{k + 1:03d}@{C.VPA_DOMAIN}"
            name = target.display_name  # the swapped QR shows the shop's name
        else:
            target = None
            stem = _SCAM_VPA_STEMS[archetype][k % 3]
            vpa = f"{stem}.{k + 1:03d}@{C.VPA_DOMAIN}"
            name = stem.replace(".", " ").title()
        acct = world.add_account(
            Account(
                account_id=f"acct_s{n:05d}",
                vpa=vpa,
                account_type="scammer",
                display_name=name,
                home_city=world.random_city(),
                created_at=created,
                archetype=archetype,
            )
        )
        if k < 4:
            device, phone = pool[k % 2]
        else:
            device, phone = world.device_id(), world.phone_id()
        world.add_device(acct.account_id, device, phone, created, True)
        out.append((acct, (start, end), target))
    return out


def build_archetypes(world: World) -> None:
    rng = world.rng
    for archetype in C.ARCHETYPES:
        spec = C.ARCHETYPE_SPECS[archetype]
        operators = _operator_accounts(world, archetype)
        weights = [3 if k < 2 else 2 for k in range(len(operators))]
        for _ in range(spec.victims):
            acct, (start, end), target = rng.choices(operators, weights)[0]
            if target is not None:  # QR swap: a regular customer of the targeted shop
                regulars = [u for u in world.users if target.vpa in u.merchants]
                victim = rng.choice(regulars or world.users)
            else:
                victim = rng.choice(world.users)
            ts = world.random_ts(start, end)
            amount = _scammy_amount(world, *spec.amount_range)
            device = None
            if rng.random() < spec.device_changed_p:
                device = _scam_session_device(world, victim.account.account_id, ts)
            first = world.add(
                Intent(
                    ts=ts,
                    payer_id=victim.account.account_id,
                    payee_vpa=acct.vpa,
                    amount=amount,
                    channel=spec.channel,
                    message_context=scam_message(
                        rng, archetype, amount, target.display_name if target else ""
                    ),
                    device_id=device,
                    added_minutes_before=rng.uniform(0.2, 2)
                    if archetype == "qr_swap"
                    else rng.uniform(0.5, 25),
                    is_scam=True,
                    scam_type=archetype,
                    intended_payee_vpa=target.vpa if target else None,
                )
            )
            if rng.random() < spec.burst_p:  # pays again within the hour
                ts2 = ts + timedelta(minutes=rng.uniform(3, 50))
                if ts2 <= C.AS_OF:
                    world.add(
                        Intent(
                            ts=ts2,
                            payer_id=first.payer_id,
                            payee_vpa=acct.vpa,
                            amount=_scammy_amount(world, *spec.amount_range),
                            channel=spec.channel,
                            message_context=first.message_context,
                            device_id=device,
                            is_scam=True,
                            scam_type=archetype,
                        )
                    )


def build_mule_rings(world: World) -> None:
    """Mule rings: shared devices/phones, many victims paying one collector VPA, then layering."""
    rng, fake = world.rng, world.fake
    for ring in C.MULE_RINGS:
        devices = [world.device_id() for _ in range(3)]
        phones = [world.phone_id() for _ in range(2)]
        start = C.AS_OF - timedelta(days=ring.active_days[0])
        end = C.AS_OF - timedelta(days=ring.active_days[1])
        members: list[Account] = []
        for k in range(ring.members):
            first, last = fake.first_name(), fake.last_name()
            n = 90_000 + len(world.accounts)
            acct = world.add_account(
                Account(
                    account_id=f"acct_mule_{ring.ring_id}_{k + 1:02d}",
                    vpa=world.person_vpa(first, last, n),
                    account_type="mule",
                    display_name=f"{first} {last}",
                    home_city=world.random_city(),
                    created_at=start - timedelta(days=rng.uniform(20, 300)),
                    ring_id=ring.ring_id,
                )
            )
            # The collector uses two of the ring's handsets; everyone shares at least one.
            for d in sorted(rng.sample(range(3), 2 if k == 0 else rng.randint(1, 2))):
                world.add_device(
                    acct.account_id, devices[d], phones[d % 2], acct.created_at, d == 0
                )
            members.append(acct)
        collector, backup, cashout = members[0], members[1], members[-1]

        victims = rng.sample(world.users, ring.victims)
        for i, victim in enumerate(victims):
            if i < ring.victims_last_24h:
                ts = world.random_ts(C.AS_OF - timedelta(hours=23), C.AS_OF)
            else:
                ts = world.random_ts(
                    start, end - timedelta(hours=24) if ring.victims_last_24h else end
                )
            payee = backup if rng.random() < 0.15 else collector
            amount = _scammy_amount(world, *ring.amount_range)
            world.add(
                Intent(
                    ts=ts,
                    payer_id=victim.account.account_id,
                    payee_vpa=payee.vpa,
                    amount=amount,
                    channel="p2p",
                    message_context=scam_message(rng, ring.scheme, amount),
                    added_minutes_before=rng.uniform(0.5, 20),
                    is_scam=True,
                    scam_type=ring.scheme,
                    ring_id=ring.ring_id,
                )
            )
            # Layering: the money hops to another member, sometimes on to the cash-out account.
            hop_ts = ts + timedelta(minutes=rng.uniform(5, 90))
            hop_to = rng.choice(members[2:-1]) if len(members) > 3 else cashout
            for payer, payee_acct, share in ((payee, hop_to, 0.9), (hop_to, cashout, 0.85)):
                if hop_ts > C.AS_OF or (payee_acct is cashout and rng.random() < 0.6):
                    break
                amount = float(round(amount * share * rng.uniform(0.9, 1.0)))
                world.add(
                    Intent(
                        ts=hop_ts,
                        payer_id=payer.account_id,
                        payee_vpa=payee_acct.vpa,
                        amount=amount,
                        channel="p2p",
                        device_id=next(
                            r["device_id"]
                            for r in world.device_rows
                            if r["account_id"] == payer.account_id
                        ),
                        city=payer.home_city,
                        is_scam=True,
                        scam_type="mule_layering",
                        ring_id=ring.ring_id,
                    )
                )
                hop_ts += timedelta(minutes=rng.uniform(10, 120))
