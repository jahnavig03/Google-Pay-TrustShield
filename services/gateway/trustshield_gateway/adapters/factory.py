"""Build the adapter set for the current TRUSTSHIELD_MODE."""

from __future__ import annotations

from dataclasses import dataclass

from ..ports import DocumentStore, Publisher
from ..settings import doc_store_backend, mode, project_id, publisher_backend
from .memory_store import MemoryDocumentStore
from .noop_publisher import NoopPublisher


@dataclass(frozen=True)
class Services:
    mode: str
    store: DocumentStore
    publisher: Publisher
    store_backend: str
    publisher_backend: str


def build_services() -> Services:
    current_mode = mode()
    store_kind, publisher_kind = doc_store_backend(), publisher_backend()

    if store_kind == "firestore":
        from .firestore_store import FirestoreDocumentStore

        store: DocumentStore = FirestoreDocumentStore(project_id())
    elif store_kind == "memory":
        store = MemoryDocumentStore()
    else:
        raise ValueError(
            f"TRUSTSHIELD_DOC_STORE must be 'firestore' or 'memory', got {store_kind!r}"
        )

    if publisher_kind == "pubsub":
        from .pubsub_publisher import PubSubPublisher

        publisher: Publisher = PubSubPublisher(project_id())
    elif publisher_kind == "noop":
        publisher = NoopPublisher()
    else:
        raise ValueError(
            f"TRUSTSHIELD_PUBLISHER must be 'pubsub' or 'noop', got {publisher_kind!r}"
        )

    return Services(current_mode, store, publisher, store_kind, publisher_kind)
