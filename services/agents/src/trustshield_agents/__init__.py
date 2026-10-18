"""TrustShield agent layer.

from trustshield_agents import evaluate_payment, verify_merchant_payment, answer_case_question
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

__version__ = "0.1.0"

if TYPE_CHECKING:
    from .investigator import answer_case_question, policy_citations
    from .merchant import verify_merchant_payment
    from .service import evaluate_payment, evaluate_payment_async, warm_up, warm_up_async

__all__ = [
    "answer_case_question",
    "evaluate_payment",
    "evaluate_payment_async",
    "policy_citations",
    "verify_merchant_payment",
    "warm_up",
    "warm_up_async",
]


def __getattr__(name: str) -> Any:
    # Lazy so `python -m trustshield_agents.risk` doesn't import ADK.
    if name == "verify_merchant_payment":  # PayGuard; doesn't import ADK
        from .merchant import verify_merchant_payment

        return verify_merchant_payment
    if name in ("answer_case_question", "policy_citations"):  # Investigator; doesn't import ADK
        from . import investigator

        return getattr(investigator, name)
    if name in __all__:
        from . import service

        return getattr(service, name)
    raise AttributeError(name)
