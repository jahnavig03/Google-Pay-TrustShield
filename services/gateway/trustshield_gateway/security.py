"""Demo role check. ``X-Demo-Role`` stands in for real auth in the prototype."""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated

from fastapi import Header, HTTPException, status

ROLE_HEADER = "X-Demo-Role"
CUSTOMER, ANALYST, MERCHANT = "customer", "analyst", "merchant"
KNOWN_ROLES = frozenset({CUSTOMER, ANALYST, MERCHANT})


def require_role(*allowed: str) -> Callable[[str | None], str]:
    """Dependency factory: the caller must send ``X-Demo-Role`` with one of ``allowed``."""
    permitted = frozenset(allowed)

    def dependency(
        x_demo_role: Annotated[str | None, Header(alias=ROLE_HEADER)] = None,
    ) -> str:
        role = (x_demo_role or "").strip().lower()
        if not role:
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED,
                detail=f"{ROLE_HEADER} header is required ({', '.join(sorted(KNOWN_ROLES))}).",
            )
        if role not in permitted:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                detail=f"This endpoint needs {ROLE_HEADER}: {', '.join(sorted(permitted))}.",
            )
        return role

    return dependency
