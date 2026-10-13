"""Pub/Sub publisher for gcp mode. The client is blocking, so publishes run on a worker thread."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from google.cloud import pubsub_v1


class PubSubPublisher:
    def __init__(self, project: str) -> None:
        self._project = project
        self._client = pubsub_v1.PublisherClient()

    async def publish(self, topic: str, payload: dict[str, Any]) -> str:
        path = self._client.topic_path(self._project, topic)
        data = json.dumps(payload).encode("utf-8")
        future = await asyncio.to_thread(self._client.publish, path, data)
        return await asyncio.to_thread(future.result)

    async def close(self) -> None:
        await asyncio.to_thread(self._client.stop)
