"""TrustShield agent layer.

from trustshield_agents import evaluate_payment
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

__version__ = "0.1.0"

if TYPE_CHECKING:
    from .service import evaluate_payment, evaluate_payment_async, warm_up, warm_up_async

__all__ = ["evaluate_payment", "evaluate_payment_async", "warm_up", "warm_up_async"]


def __getattr__(name: str) -> Any:
    # Lazy so `python -m trustshield_agents.risk` doesn't import ADK.
    if name in __all__:
        from . import service

        return getattr(service, name)
    raise AttributeError(name)
