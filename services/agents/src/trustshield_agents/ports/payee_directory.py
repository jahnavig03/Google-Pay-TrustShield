from __future__ import annotations

from typing import Protocol


class PayeeDirectory(Protocol):
    """Registered (KYC) display name per UPI ID. Used to check the name printed in a QR code."""

    async def registered_name(self, payee_vpa: str) -> str | None: ...
