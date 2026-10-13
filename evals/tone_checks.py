"""Tone rules for customer-facing output (PRD §8 Tone + Privacy).

Flags: accusatory / alarming wording, any request for (or mention of) PIN / OTP / password /
CVV / card number, and missing safe actions.
"""

from __future__ import annotations

import re

ACCUSATORY = re.compile(
    r"\b(fraudster|scammer|criminal|thief|cheat(er)?|you (were|are being|have been) "
    r"(scammed|fooled|tricked|cheated)|your (fault|mistake)|careless|stupid|foolish|"
    r"should have known|suspicious person|fake (person|seller|buyer))\b",
    re.IGNORECASE,
)
ALARMING = re.compile(r"\b(fraud|scam|fake|criminal|illegal)\b", re.IGNORECASE)
CREDENTIALS = re.compile(
    r"\b(otp|one[- ]time password|upi pin|atm pin|m-?pin|pin|password|passcode|cvv|"
    r"card number|card no\.?)\b",
    re.IGNORECASE,
)
ACTION_WORDS = re.compile(
    r"\b(cancel|verify|check|confirm|call|contact|decline|go ahead|continue|pause|"
    r"don't proceed|report)\b",
    re.IGNORECASE,
)


def check_customer_text(text: str) -> list[str]:
    """Violations in one piece of customer-facing text."""
    problems = []
    if ACCUSATORY.search(text):
        problems.append("accusatory")
    if ALARMING.search(text):
        problems.append("alarming_word")
    if CREDENTIALS.search(text):
        problems.append("credential_mention")
    return problems


def check_response(resp: dict) -> list[str]:
    """Violations in a PaymentRiskResponse (as a JSON dict)."""
    problems = [f"message:{p}" for p in check_customer_text(resp.get("customer_message", ""))]
    for signal in resp.get("top_signals", []):
        problems += [
            f"signal:{p}" for p in check_customer_text(signal.get("plain_explanation", ""))
        ]
    for action in resp.get("safe_actions", []):
        problems += [f"action:{p}" for p in check_customer_text(action.get("label", ""))]
    if not resp.get("safe_actions"):
        problems.append("missing_safe_actions")
    if not ACTION_WORDS.search(resp.get("customer_message", "")):
        problems.append("message_has_no_next_action")
    return problems


if __name__ == "__main__":
    import json
    import sys

    for line in sys.stdin:
        print(check_response(json.loads(line)))
