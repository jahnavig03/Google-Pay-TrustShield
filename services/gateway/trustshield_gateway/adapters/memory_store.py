"""In-process document store. Used in mock mode when no Firestore emulator is configured."""

from __future__ import annotations

import asyncio
import copy
from typing import Any

from ..ports import AlreadyExists


class MemoryDocumentStore:
    """Dict-backed stand-in for Firestore. Deep-copies on the way in and out."""

    def __init__(self) -> None:
        self._data: dict[str, dict[str, dict[str, Any]]] = {}
        self._lock = asyncio.Lock()

    async def create(self, collection: str, doc_id: str, data: dict[str, Any]) -> None:
        async with self._lock:
            documents = self._data.setdefault(collection, {})
            if doc_id in documents:
                raise AlreadyExists(collection, doc_id)
            documents[doc_id] = copy.deepcopy(data)

    async def get(self, collection: str, doc_id: str) -> dict[str, Any] | None:
        async with self._lock:
            found = self._data.get(collection, {}).get(doc_id)
            return copy.deepcopy(found) if found is not None else None

    async def list(
        self, collection: str, *, order_by: str | None = None, descending: bool = True
    ) -> list[dict[str, Any]]:
        async with self._lock:
            docs = [copy.deepcopy(doc) for doc in self._data.get(collection, {}).values()]
        if order_by:
            docs.sort(key=lambda doc: str(doc.get(order_by) or ""), reverse=descending)
        return docs

    async def update(self, collection: str, doc_id: str, patch: dict[str, Any]) -> None:
        async with self._lock:
            existing = self._data.get(collection, {}).get(doc_id)
            if existing is None:
                raise KeyError(f"{collection}/{doc_id} does not exist")
            existing.update(copy.deepcopy(patch))

    async def append(self, collection: str, doc_id: str, field: str, item: Any) -> None:
        async with self._lock:
            existing = self._data.get(collection, {}).get(doc_id)
            if existing is None:
                raise KeyError(f"{collection}/{doc_id} does not exist")
            existing.setdefault(field, []).append(copy.deepcopy(item))

    async def update_if_greater(
        self, collection: str, doc_id: str, field: str, value: float, patch: dict[str, Any]
    ) -> bool:
        async with self._lock:
            existing = self._data.get(collection, {}).get(doc_id)
            if existing is None:
                raise KeyError(f"{collection}/{doc_id} does not exist")
            current = existing.get(field)
            if current is not None and current >= value:
                return False
            existing.update({field: value, **copy.deepcopy(patch)})
            return True

    async def close(self) -> None:
        return None
