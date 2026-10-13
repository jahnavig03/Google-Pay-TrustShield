"""No-op publisher for mock mode: records what would have been published, sends nothing."""

from __future__ import annotations

import logging
import uuid
from typing import Any

log = logging.getLogger(__name__)


class NoopPublisher:
    def __init__(self) -> None:
        self.published: list[tuple[str, dict[str, Any]]] = []

    async def publish(self, topic: str, payload: dict[str, Any]) -> str:
        self.published.append((topic, payload))
        log.info("pubsub (mock, not sent) topic=%s payload=%s", topic, payload)
        return f"mock-{uuid.uuid4().hex[:12]}"

    async def close(self) -> None:
        return None
