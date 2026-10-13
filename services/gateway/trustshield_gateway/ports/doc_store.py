"""Document store port: Firestore collections (``audit_log``, ``cases``, ``approvals``)."""

from __future__ import annotations

from typing import Any, Protocol


class DocumentStore(Protocol):
    """A small slice of Firestore: create, read, list and patch documents in a collection."""

    async def create(self, collection: str, doc_id: str, data: dict[str, Any]) -> None:
        """Write a document. Overwrites an existing document with the same id."""
        ...

    async def get(self, collection: str, doc_id: str) -> dict[str, Any] | None: ...

    async def list(
        self, collection: str, *, order_by: str | None = None, descending: bool = True
    ) -> list[dict[str, Any]]: ...

    async def update(self, collection: str, doc_id: str, patch: dict[str, Any]) -> None:
        """Merge ``patch`` into an existing document."""
        ...

    async def close(self) -> None: ...
