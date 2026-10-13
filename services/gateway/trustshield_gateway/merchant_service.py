"""PayGuard ledger check.

One function so the real implementation can be swapped in without touching the route: once
Ronak's ``trustshield_agents.verify_merchant_payment`` exists, this delegates to it.
"""

from __future__ import annotations

from trustshield_contracts import (
    MerchantVerifyRequest,
    MerchantVerifyResponse,
    PaymentStatus,
    RiskLevel,
)

#: What the stub did look at. Governance rule 2 needs a non-empty evidence trail.
LEDGER_LOOKUP_EVIDENCE_ID = "merchant_ledger_lookup"

_STUB_EXPLANATION = (
    "No settled credit matching this transaction id and amount appears in the merchant ledger "
    "yet. A genuine payment can also take a few minutes to settle, so this is not proof of "
    "anything on its own."
)
_STUB_ACTION = (
    "Hold the goods for now and check your settlement list in your merchant app. If the credit "
    "has not arrived in a few minutes, ask the customer to pay again while you watch for it."
)


def _agents_verifier():
    """Ronak's screenshot verifier, or None while it is still being built."""
    try:
        import trustshield_agents
    except ImportError:  # pragma: no cover - the gateway always installs the agents package
        return None
    return getattr(trustshield_agents, "verify_merchant_payment", None)


async def verify_merchant_payment(
    req: MerchantVerifyRequest,
) -> tuple[MerchantVerifyResponse, list[str]]:
    """Return the verification result and the evidence ids behind it."""
    verifier = _agents_verifier()
    if verifier is not None:
        response = await verifier(req)
        return response, list(getattr(response, "evidence_ids", []) or [LEDGER_LOOKUP_EVIDENCE_ID])

    response = MerchantVerifyResponse(
        payment_status=PaymentStatus.NOT_FOUND_IN_LEDGER,
        risk_level=RiskLevel.MEDIUM,
        extracted=None,
        recommended_action=_STUB_ACTION,
        explanation=_STUB_EXPLANATION,
    )
    return response, [LEDGER_LOOKUP_EVIDENCE_ID]
