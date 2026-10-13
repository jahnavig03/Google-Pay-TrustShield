"""Firestore document store: the local emulator in mock mode, real Firestore in gcp mode.

``google-cloud-firestore`` picks up ``FIRESTORE_EMULATOR_HOST`` on its own and uses anonymous
credentials when it is set, so the same adapter serves both modes.
"""

from __future__ import annotations

from typing import Any

from google.api_core import exceptions as gcp_exceptions
from google.cloud import firestore

from ..ports import AlreadyExists


class FirestoreDocumentStore:
    def __init__(self, project: str) -> None:
        self._client = firestore.AsyncClient(project=project)

    async def create(self, collection: str, doc_id: str, data: dict[str, Any]) -> None:
        # .create() rather than .set(): Firestore rejects it if the document already exists,
        # so an append-only collection cannot be overwritten even by a concurrent writer.
        try:
            await self._client.collection(collection).document(doc_id).create(data)
        except (gcp_exceptions.AlreadyExists, gcp_exceptions.Conflict) as exc:
            # Firestore reports the clash as AlreadyExists; some transports surface the same
            # condition as a plain 409 Conflict. Both mean the id is taken.
            raise AlreadyExists(collection, doc_id) from exc

    async def get(self, collection: str, doc_id: str) -> dict[str, Any] | None:
        snapshot = await self._client.collection(collection).document(doc_id).get()
        return snapshot.to_dict() if snapshot.exists else None

    async def list(
        self, collection: str, *, order_by: str | None = None, descending: bool = True
    ) -> list[dict[str, Any]]:
        # Sorting happens in Python: the emulator has no composite indexes, and the demo
        # collections are small.
        docs = [
            snapshot.to_dict() async for snapshot in self._client.collection(collection).stream()
        ]
        docs = [doc for doc in docs if doc is not None]
        if order_by:
            docs.sort(key=lambda doc: str(doc.get(order_by) or ""), reverse=descending)
        return docs

    async def update(self, collection: str, doc_id: str, patch: dict[str, Any]) -> None:
        await self._client.collection(collection).document(doc_id).update(patch)

    async def close(self) -> None:
        self._client.close()
