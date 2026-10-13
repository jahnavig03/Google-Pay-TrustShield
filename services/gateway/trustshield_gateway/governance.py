"""Governance: the four rules in CLAUDE.md, enforced here and nowhere else.

1. Hold, restrict and escalate require a human (analyst) approval record.
2. If there are no ``evidence_ids``, the action is blocked.
3. Any customer message that asks for a PIN, OTP, password or full card number is blocked,
   not cleaned up.
4. Every decision gets an ``audit_id`` and is written to the Firestore ``audit_log`` collection.

Rules 2 and 3 are checked by :func:`review` before anything is returned to a caller. Rule 1 is
checked by :func:`require_approval` at the point an action is executed. Rule 4 is carried out by
:mod:`trustshield_gateway.audit`, which every route goes through.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from trustshield_contracts import AnalystAction, Decision, GovernanceOutcome

#: Actions that may only be executed once an analyst has recorded an approval (rule 1).
ACTIONS_REQUIRING_APPROVAL: frozenset[str] = frozenset(
    {"hold", "restrict", "escalate", AnalystAction.APPROVE_ESCALATION.value}
)

#: Decisions the agents may recommend but the gateway may not execute on its own (rule 1).
DECISIONS_REQUIRING_APPROVAL: frozenset[Decision] = frozenset({Decision.HOLD_AND_ESCALATE})

# Rule 3. Any mention of these credentials in customer-facing text is treated as a request for
# them: a safe message never needs to name them. The agents service applies the same check to its
# own output; repeating it here keeps Governance self-contained and independently testable.
_SENSITIVE_CREDENTIALS = re.compile(
    r"\b(otp|one[- ]time password|upi[- ]?pin|atm[- ]?pin|m-?pin|pin|password|passcode|"
    r"cvv|cvc|card number|card no\.?|full card(?: number)?|card details)\b",
    re.IGNORECASE,
)

#: Status returned when rule 2 or rule 3 blocks an action. Spelled out rather than taken from
#: starlette.status, whose name for it changed between releases.
HTTP_422_BLOCKED = 422

BLOCK_NO_EVIDENCE = "no_evidence_ids"
BLOCK_SENSITIVE_CREDENTIALS = "customer_message_requests_credentials"

_BLOCK_REASONS = {
    BLOCK_NO_EVIDENCE: (
        "Governance rule 2: the decision cites no evidence, so the action is blocked."
    ),
    BLOCK_SENSITIVE_CREDENTIALS: (
        "Governance rule 3: the customer message refers to a PIN, OTP, password, CVV or card "
        "number. Such a message is blocked, never edited and sent."
    ),
}


class GovernanceBlocked(Exception):
    """Rule 2 or rule 3 failed. The caller writes a ``blocked`` audit row and returns HTTP 422."""

    def __init__(self, code: str) -> None:
        super().__init__(_BLOCK_REASONS.get(code, code))
        self.code = code
        self.reason = _BLOCK_REASONS.get(code, code)


class ApprovalRequired(Exception):
    """Rule 1 failed: an action needing analyst approval was executed without one (HTTP 409)."""

    def __init__(self, action: str) -> None:
        self.action = action
        self.reason = (
            f"Governance rule 1: '{action}' may only be executed after an analyst has recorded "
            "an approval decision."
        )
        super().__init__(self.reason)


@dataclass(frozen=True)
class Verdict:
    """The outcome Governance records for a decision that passed rules 2 and 3."""

    outcome: GovernanceOutcome
    reason: str | None = None


def mentions_sensitive_credentials(text: str) -> bool:
    """Rule 3 predicate."""
    return bool(_SENSITIVE_CREDENTIALS.search(text or ""))


def check_evidence(evidence_ids: list[str]) -> None:
    """Rule 2. Raises :class:`GovernanceBlocked` when nothing was retrieved."""
    if not evidence_ids:
        raise GovernanceBlocked(BLOCK_NO_EVIDENCE)


def check_customer_text(text: str) -> None:
    """Rule 3. Raises :class:`GovernanceBlocked`; never rewrites the text."""
    if mentions_sensitive_credentials(text):
        raise GovernanceBlocked(BLOCK_SENSITIVE_CREDENTIALS)


def require_approval(action: str, approval_record_id: str | None) -> None:
    """Rule 1. Raises :class:`ApprovalRequired` when a gated action has no approval record."""
    if action in ACTIONS_REQUIRING_APPROVAL and not approval_record_id:
        raise ApprovalRequired(action)


def review(*, evidence_ids: list[str], customer_message: str, decision: Decision | None) -> Verdict:
    """Run rules 2 and 3 over an agent decision, then classify it for the audit row.

    A ``HOLD_AND_ESCALATE`` is recorded as ``needs_approval``: the gateway returns it to the
    customer as a recommendation and opens a case, but never executes the hold itself (rule 1).
    """
    check_evidence(evidence_ids)
    check_customer_text(customer_message)
    if decision in DECISIONS_REQUIRING_APPROVAL:
        return Verdict(
            GovernanceOutcome.NEEDS_APPROVAL,
            "Hold recommended to the customer; execution needs an analyst approval record.",
        )
    return Verdict(GovernanceOutcome.PERMITTED)
