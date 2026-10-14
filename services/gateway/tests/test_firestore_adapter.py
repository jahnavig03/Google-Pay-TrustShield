"""FirestoreDocumentStore against a stubbed client.

The adapter is thin, but it is the only store that runs in gcp mode, so its mapping onto the
Firestore API is worth pinning down. The real emulator is exercised by the test in
test_payment_flow.py, which skips itself unless FIRESTORE_EMULATOR_HOST is reachable.
"""

from __future__ import annotations

import sys
import types
from typing import Any

import pytest
from google.api_core import exceptions as gcp_exceptions


class _Snapshot:
    def __init__(self, data: dict[str, Any] | None) -> None:
        self._data = data
        self.exists = data is not None

    def to_dict(self) -> dict[str, Any] | None:
        return self._data


class _ArrayUnion:
    """Stand-in for firestore.ArrayUnion: the stub's update() appends its values."""

    def __init__(self, values: list[Any]) -> None:
        self.values = values


class _Document:
    def __init__(self, collection: _Collection, doc_id: str) -> None:
        self._collection, self._id = collection, doc_id

    async def create(self, data: dict[str, Any]) -> None:
        # Matches Firestore: create fails if the document is already there.
        self._collection.calls.append("create")
        if self._id in self._collection.docs:
            raise self._collection.conflict_error(f"{self._id} already exists")
        self._collection.docs[self._id] = dict(data)

    async def set(self, data: dict[str, Any]) -> None:
        # Present only so a regression back to .set() is visible in `calls`.
        self._collection.calls.append("set")
        self._collection.docs[self._id] = dict(data)

    async def get(self) -> _Snapshot:
        return _Snapshot(self._collection.docs.get(self._id))

    async def update(self, patch: dict[str, Any]) -> None:
        if self._id not in self._collection.docs:
            raise KeyError(self._id)
        doc = self._collection.docs[self._id]
        for key, value in patch.items():
            if isinstance(value, _ArrayUnion):
                self._collection.calls.append("array_union")
                doc.setdefault(key, []).extend(v for v in value.values if v not in doc[key])
            else:
                doc[key] = value


class _Collection:
    #: Swapped per test to check both exception types Firestore can raise for a taken id.
    conflict_error: Any = gcp_exceptions.AlreadyExists

    def __init__(self) -> None:
        self.docs: dict[str, dict[str, Any]] = {}
        self.calls: list[str] = []

    def document(self, doc_id: str) -> _Document:
        return _Document(self, doc_id)

    async def stream(self):
        for data in list(self.docs.values()):
            yield _Snapshot(data)


class _FakeAsyncClient:
    def __init__(self, project: str) -> None:
        self.project = project
        self.closed = False
        self._collections: dict[str, _Collection] = {}

    def collection(self, name: str) -> _Collection:
        return self._collections.setdefault(name, _Collection())

    def calls_on(self, name: str) -> list[str]:
        return self._collections[name].calls

    def close(self) -> None:
        self.closed = True


@pytest.fixture
def store(monkeypatch):
    """Import the adapter with google.cloud.firestore replaced by the stub above."""
    fake_module = types.SimpleNamespace(AsyncClient=_FakeAsyncClient, ArrayUnion=_ArrayUnion)
    monkeypatch.setitem(sys.modules, "google.cloud.firestore", fake_module)
    sys.modules.pop("trustshield_gateway.adapters.firestore_store", None)

    from trustshield_gateway.adapters.firestore_store import FirestoreDocumentStore

    created = FirestoreDocumentStore("trustshield-local")
    yield created
    sys.modules.pop("trustshield_gateway.adapters.firestore_store", None)


async def test_create_then_get(store):
    await store.create("audit_log", "AUD-1", {"audit_id": "AUD-1", "decision": "ALLOW"})
    assert await store.get("audit_log", "AUD-1") == {"audit_id": "AUD-1", "decision": "ALLOW"}


async def test_get_missing_document_is_none(store):
    assert await store.get("audit_log", "nope") is None


async def test_list_orders_newest_first(store):
    await store.create("cases", "a", {"case_id": "a", "created_at": "2026-10-13T09:00:00Z"})
    await store.create("cases", "b", {"case_id": "b", "created_at": "2026-10-13T11:00:00Z"})
    await store.create("cases", "c", {"case_id": "c", "created_at": "2026-10-13T10:00:00Z"})

    rows = await store.list("cases", order_by="created_at", descending=True)
    assert [row["case_id"] for row in rows] == ["b", "c", "a"]

    rows = await store.list("cases", order_by="created_at", descending=False)
    assert [row["case_id"] for row in rows] == ["a", "c", "b"]


async def test_list_without_order_by_returns_everything(store):
    await store.create("approvals", "APPR-1", {"approval_record_id": "APPR-1"})
    assert len(await store.list("approvals")) == 1


async def test_update_merges_into_the_existing_document(store):
    await store.create("cases", "CASE-1", {"case_id": "CASE-1", "status": "pending_approval"})
    await store.update("cases", "CASE-1", {"status": "escalated"})
    assert await store.get("cases", "CASE-1") == {"case_id": "CASE-1", "status": "escalated"}


async def test_close_closes_the_client(store):
    await store.close()
    assert store._client.closed is True


async def test_create_refuses_to_overwrite_an_existing_document(store):
    """Governance rule 4: audit_log is append-only, so a repeat id must fail, not replace."""
    from trustshield_gateway.ports import AlreadyExists

    await store.create("audit_log", "AUD-1", {"audit_id": "AUD-1", "decision": "ALLOW"})
    with pytest.raises(AlreadyExists):
        await store.create("audit_log", "AUD-1", {"audit_id": "AUD-1", "decision": "HOLD"})

    # The original survives untouched.
    assert (await store.get("audit_log", "AUD-1"))["decision"] == "ALLOW"


async def test_create_uses_firestore_create_not_set(store):
    """Regression guard: .set() would overwrite and break the append-only audit log."""
    await store.create("audit_log", "AUD-9", {"audit_id": "AUD-9"})
    calls = store._client.calls_on("audit_log")
    assert calls == ["create"]
    assert "set" not in calls


async def test_conflict_is_translated_to_the_port_error(store):
    """Some transports surface a taken id as a plain 409 Conflict rather than AlreadyExists."""
    from trustshield_gateway.ports import AlreadyExists

    collection = store._client.collection("audit_log")
    collection.conflict_error = gcp_exceptions.Conflict

    await store.create("audit_log", "AUD-C", {"audit_id": "AUD-C"})
    with pytest.raises(AlreadyExists):
        await store.create("audit_log", "AUD-C", {"audit_id": "AUD-C"})


async def test_append_uses_array_union_not_read_modify_write(store):
    """Server-side ArrayUnion is what makes concurrent timeline appends safe."""
    await store.create("cases", "CASE-1", {"case_id": "CASE-1", "timeline": [{"n": 0}]})
    await store.append("cases", "CASE-1", "timeline", {"n": 1})
    assert (await store.get("cases", "CASE-1"))["timeline"] == [{"n": 0}, {"n": 1}]
    assert store._client.calls_on("cases") == ["create", "array_union"]
