"""Plain-language, non-accusatory explanation templates for each risk signal.

Signals describe what was observed, never who is to blame, and make no policy claims
(policy statements need a cited source and belong in the customer message).
"""

from __future__ import annotations

from .features import RiskInputs

CODES = {
    "A": "amount_deviation",
    "B": "new_beneficiary",
    "D": "device_anomaly",
    "L": "location_anomaly",
    "V": "velocity",
    "S": "scam_context",
    "N": "mule_network",
}

_SCAM_TEXT: dict[str, tuple[str, str]] = {
    "urgency": (
        "Urgent message",
        "The message linked to this payment asks you to pay immediately.",
    ),
    "fake_kyc": (
        "KYC update request",
        "The message linked to this payment asks you to pay to update your KYC.",
    ),
    "fake_refund": (
        "Refund offer",
        (
            "The message linked to this payment offers a refund but asks you to pay or approve "
            "a request first."
        ),
    ),
    "receive_money_first": (
        "'Receive money' request",
        (
            "The message says you will receive money, but this request would take money from "
            "your account."
        ),
    ),
    "impersonation": (
        "Message claims an official source",
        "The message linked to this payment claims to be from an official, bank or company.",
    ),
    "qr_swap": (
        "QR code mismatch",
        "The QR code may not belong to the person or shop you intend to pay.",
    ),
    "none": (
        "Unusual message",
        (
            "The message linked to this payment has wording often seen in payment requests "
            "that turned out to be unsafe."
        ),
    ),
}


def _human_age(minutes: int) -> str:
    if minutes < 60:
        n, unit = max(minutes, 1), "minute"
    elif minutes < 60 * 48:
        n, unit = minutes // 60, "hour"
    else:
        n, unit = minutes // (60 * 24), "day"
    return f"{n} {unit}{'' if n == 1 else 's'}"


def _rupees(x: float) -> str:
    return f"₹{x:,.0f}"


def explain(key: str, x: float, fired: bool, inputs: RiskInputs, median: float) -> tuple[str, str]:
    """(label, plain_explanation) for feature ``key`` with normalised value ``x``.

    ``fired`` = the signal contributed meaningfully to R. Non-fired signals get reassuring
    wording; they only appear as padding so the customer still sees 3 explained signals.
    """
    if key == "A":
        if not fired:
            return "Usual amount", "This amount is in line with your usual payments."
        ratio = inputs.amount / max(median, 1.0)
        if ratio >= 2.5:
            text = (
                f"This amount is about {ratio:.0f} times your usual payment of {_rupees(median)}."
            )
        else:
            text = f"This amount is higher than your usual payment of {_rupees(median)}."
        return "Unusually large amount", text

    if key == "B":
        reported = "reported_by_users" in inputs.beneficiary_flags
        recent = inputs.beneficiary_age_minutes < 60 * 24 * 7
        if not fired:
            if recent:
                age = _human_age(inputs.beneficiary_age_minutes)
                return "Recipient", f"The recipient was added {age} ago."
            return "Known recipient", "You have had this recipient for a while."
        parts = []
        if recent:
            parts.append(
                f"The recipient was added {_human_age(inputs.beneficiary_age_minutes)} ago."
            )
        if reported:
            parts.append("Other users have recently reported concerns about this recipient.")
        if not parts:
            parts.append("This recipient's account was created recently.")
        label = "New recipient" if recent else "Recipient with recent reports"
        return label, " ".join(parts)

    if key == "D":
        if not fired:
            return "Usual device", "You're paying from a device you've used before."
        return "New device", "This payment is being made from a device you haven't used before."

    if key == "L":
        if not fired:
            return "Usual location", "You're paying from a place you usually pay from."
        return (
            "Unusual location",
            "This payment is being made from a place you don't usually pay from.",
        )

    if key == "V":
        if not fired:
            return "Normal activity", "Your payment activity today looks normal."
        return "More payments than usual", "You've made more payments today than you usually do."

    if key == "S":
        if not fired:
            if inputs.has_message:
                return (
                    "Message checked",
                    "No pressure tactics were found in the message you shared.",
                )
            return "No message shared", "No message or screenshot was shared with this payment."
        label, text = _SCAM_TEXT.get(inputs.scam_pattern, _SCAM_TEXT["none"])
        if "account_block" in inputs.scam_cues:
            text = (
                "The message linked to this payment says your account will be blocked "
                "unless you pay now."
            )
        return label, text

    if key == "N":
        if not fired:
            return "No reported links", "No links to recently reported accounts were found."
        if inputs.payee_reported_links > 0:
            return (
                "Recipient linked to reported accounts",
                "The recipient's account is linked to other accounts that were recently reported.",
            )
        return (
            "Many payments to this recipient",
            "The recipient has received money from many different people in the last day.",
        )

    raise KeyError(key)
