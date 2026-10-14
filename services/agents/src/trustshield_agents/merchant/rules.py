"""Screenshot + ledger -> payment_status, risk_level, one recommended action, a plain explanation.

  verified             found in the merchant's ledger, amount / VPA / time match, settled
  pending              found, matches, not settled yet
  inconsistent         found, but the amount, VPA, transaction id or time doesn't match, it is a
                       refund rather than a credit, or it is an old payment shown again
  not_found_in_ledger  no such transaction in the merchant's ledger, no sign of editing
  suspicious           not found AND tamper hints (font mismatch, edited region, a timestamp
                       later than the moment the screenshot was shown, ...)

The ledger is the source of truth: a settled matching credit is verified whatever the image
looks like. Text is merchant-facing and neutral: it never accuses the customer and never asks
for any credential.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from trustshield_contracts import (
    ExtractedPaymentDetails,
    MerchantVerifyRequest,
    MerchantVerifyResponse,
    PaymentStatus,
    RiskLevel,
)

from .models import Extraction, LedgerEntry, MerchantRules, TamperHint, as_aware

ACTIONS = {
    PaymentStatus.VERIFIED: "The payment is in your ledger and has settled. You can hand over the goods.",
    PaymentStatus.PENDING: (
        "Wait for the credit to settle before handing over the goods. Check your settlement "
        "list again in a few minutes."
    ),
    PaymentStatus.INCONSISTENT: (
        "Hold the goods for now. Go through the payment details with the customer, or ask them "
        "to pay again while you watch for the credit."
    ),
    PaymentStatus.NOT_FOUND_IN_LEDGER: (
        "Hold the goods for now. Check your settlement list in your merchant app, or ask the "
        "customer to pay again while you watch for the credit."
    ),
    PaymentStatus.SUSPICIOUS: (
        "Hold the goods for now. Check your settlement list in your merchant app, or ask the "
        "customer to pay again while you watch for the credit."
    ),
}

_HINT_TEXT = {
    TamperHint.FONT_MISMATCH: "the amount text uses a different font from the rest of the receipt",
    TamperHint.EDITED_REGION: "part of the image looks edited",
    TamperHint.MISALIGNED_TEXT: "some text is out of line with the rest of the receipt",
    TamperHint.UNUSUAL_LAYOUT: "the layout doesn't match a standard payment receipt",
}


def _rupees(amount: float) -> str:
    return f"₹{amount:,.0f}" if float(amount).is_integer() else f"₹{amount:,.2f}"


def _minutes(delta: timedelta) -> str:
    n = max(1, round(delta.total_seconds() / 60))
    return f"{n} minute{'s' if n != 1 else ''}"


def _ago(delta: timedelta) -> str:
    hours = delta.total_seconds() / 3600
    if hours < 48:
        n = max(1, round(hours))
        return f"{n} hour{'s' if n != 1 else ''}"
    n = round(hours / 24)
    return f"{n} days"


def _join(parts: list[str], last: str = " and ") -> str:
    return parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + last + parts[-1]


def _sentence(parts: list[str]) -> str:
    """Capitalised list of clauses, ", and" before the last (the demo 3 wording)."""
    text = _join(parts, last=", and ")
    return text[0].upper() + text[1:]


def _hint_phrases(hints: list[TamperHint], ts: datetime | None, shown_at: datetime) -> list[str]:
    phrases = []
    for hint in hints:
        if hint is TamperHint.FUTURE_TIMESTAMP and ts is not None:
            phrases.append(
                f"the screenshot's timestamp is {_minutes(ts - shown_at)} after the time it was shown"
            )
        elif hint in _HINT_TEXT:
            phrases.append(_HINT_TEXT[hint])
    return phrases


def _signs(n: int) -> str:
    if n == 1:
        return "a sign the image may have been edited"
    if n == 2:
        return "both are signs the image may have been edited"
    return "all signs the image may have been edited"


def decide(
    req: MerchantVerifyRequest,
    ex: Extraction,
    entry: LedgerEntry | None,
    rules: MerchantRules,
    now: datetime,
) -> MerchantVerifyResponse:
    shown_at = as_aware(ex.shown_at) or now
    ts = as_aware(ex.timestamp)

    hints = [h for h in ex.tamper_hints if h is not TamperHint.FUTURE_TIMESTAMP]
    if ts is not None and ts - shown_at > timedelta(seconds=rules.future_tolerance_seconds):
        hints.insert(0, TamperHint.FUTURE_TIMESTAMP)

    extracted = None
    if any(v is not None for v in (ex.amount, ex.txn_id, ex.vpa, ts)):
        extracted = ExtractedPaymentDetails(
            amount=ex.amount, txn_id=ex.txn_id, vpa=ex.vpa, timestamp=ts
        )

    claimed = _rupees(req.claimed_amount)
    txn = req.claimed_transaction_id

    def respond(status: PaymentStatus, risk: RiskLevel, explanation: str) -> MerchantVerifyResponse:
        return MerchantVerifyResponse(
            payment_status=status,
            risk_level=risk,
            extracted=extracted,
            recommended_action=ACTIONS[status],
            explanation=explanation,
        )

    if entry is None:
        missing = f"No {claimed} credit with transaction ID {txn} appears in your ledger."
        phrases = _hint_phrases(hints, ts, shown_at)
        if phrases:
            return respond(
                PaymentStatus.SUSPICIOUS,
                RiskLevel.HIGH,
                f"{missing} {_sentence(phrases)} — {_signs(len(phrases))}.",
            )
        return respond(
            PaymentStatus.NOT_FOUND_IN_LEDGER,
            RiskLevel.MEDIUM,
            f"{missing} A genuine payment can take a few minutes to settle, so this is not proof "
            "of anything on its own.",
        )

    ledger_amount = _rupees(entry.amount)
    problems: list[str] = []
    amount_problem = False
    if entry.entry_type != "credit":
        problems.append(
            f"transaction {entry.txn_id} is a {entry.entry_type} you sent, not a payment you received"
        )
    # One phrase for the amount: the screenshot's if it differs, else the claimed one.
    for label, value in (("screenshot", ex.amount), ("claimed", req.claimed_amount)):
        if value is not None and abs(value - entry.amount) > rules.amount_tolerance:
            problems.append(
                f"the {label} amount is {_rupees(value)} but your ledger shows {ledger_amount}"
            )
            amount_problem = True
            break
    if ex.vpa and ex.vpa.lower() != entry.merchant_vpa.lower():
        problems.append(
            f"the screenshot shows the payment going to {ex.vpa}, not your UPI ID {entry.merchant_vpa}"
        )
    if ex.txn_id and ex.txn_id != entry.txn_id:
        problems.append(f"the screenshot shows transaction ID {ex.txn_id}, not {entry.txn_id}")
    initiated = as_aware(entry.initiated_at)
    if ts is not None and abs(ts - initiated) > timedelta(minutes=rules.time_tolerance_minutes):
        problems.append("the time on the screenshot doesn't match the time in your ledger")
    if shown_at - initiated > timedelta(hours=rules.stale_after_hours):
        problems.append(
            f"this payment was made {_ago(shown_at - initiated)} ago, so the screenshot may be "
            "from an earlier purchase"
        )
    if problems:
        return respond(
            PaymentStatus.INCONSISTENT,
            RiskLevel.HIGH if amount_problem or entry.entry_type != "credit" else RiskLevel.MEDIUM,
            f"Transaction {entry.txn_id} is in your ledger, but {_join(problems)}.",
        )
    if entry.status != "settled":
        return respond(
            PaymentStatus.PENDING,
            RiskLevel.MEDIUM,
            f"A {ledger_amount} credit with transaction ID {entry.txn_id} is in your ledger but "
            "hasn't settled yet.",
        )
    return respond(
        PaymentStatus.VERIFIED,
        RiskLevel.LOW,
        f"A {ledger_amount} credit with transaction ID {entry.txn_id} is in your ledger and has "
        "settled.",
    )
