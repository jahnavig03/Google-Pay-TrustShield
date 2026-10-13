"""Message publisher port: Pub/Sub topics (``cases``)."""

from __future__ import annotations

from typing import Any, Protocol


class Publisher(Protocol):
    async def publish(self, topic: str, payload: dict[str, Any]) -> str:
        """Publish one JSON payload. Returns a message id (synthetic for the no-op publisher)."""
        ...

    async def close(self) -> None: ...
