"""Output checks for customer-facing text (defence in depth; gateway Governance blocks too)."""

from __future__ import annotations

import re

# Any mention of these credentials in customer text is treated as a request for them.
_SENSITIVE = re.compile(
    r"\b(otp|one[- ]time password|upi pin|atm pin|m-?pin|pin|password|passcode|cvv|"
    r"card number|card no\.?|full card)\b",
    re.IGNORECASE,
)
_ACCUSATORY = re.compile(
    r"\b(fraudster|scammer|criminal|you were (scammed|fooled|tricked)|your fault|"
    r"you should have known|careless|stupid|foolish|you are being scammed)\b",
    re.IGNORECASE,
)


def mentions_sensitive_credentials(text: str) -> bool:
    return bool(_SENSITIVE.search(text))


def is_accusatory(text: str) -> bool:
    return bool(_ACCUSATORY.search(text))


def customer_text_violations(text: str) -> list[str]:
    problems = []
    if mentions_sensitive_credentials(text):
        problems.append("mentions_sensitive_credentials")
    if is_accusatory(text):
        problems.append("accusatory")
    if not text.strip():
        problems.append("empty")
    return problems
