"""Document store port: Firestore collections (``audit_log``, ``cases``, ``approvals``)."""

from __future__ import annotations

from typing import Any, Protocol


class AlreadyExists(Exception):
    """Raised by :meth:`DocumentStore.create` when the document id is already taken.

    The audit log is append-only (governance rule 4), so a write that would replace an existing
    record has to fail loudly rather than destroy it.
    """

    def __init__(self, collection: str, doc_id: str) -> None:
        self.collection, self.doc_id = collection, doc_id
        super().__init__(f"{collection}/{doc_id} already exists and must not be overwritten")


class DocumentStore(Protocol):
    """A small slice of Firestore: create, read, list and patch documents in a collection."""

    async def create(self, collection: str, doc_id: str, data: dict[str, Any]) -> None:
        """Write a NEW document. Raises :class:`AlreadyExists` if the id is already taken.

        There is deliberately no upsert: every collection the gateway owns is either
        append-only (``audit_log``, ``approvals``) or edited through :meth:`update` (``cases``).
        """
        ...

    async def get(self, collection: str, doc_id: str) -> dict[str, Any] | None: ...

    async def list(
        self, collection: str, *, order_by: str | None = None, descending: bool = True
    ) -> list[dict[str, Any]]: ...

    async def update(self, collection: str, doc_id: str, patch: dict[str, Any]) -> None:
        """Merge ``patch`` into an existing document."""
        ...

    async def close(self) -> None: ...
