"""Interfaces for every external dependency. Adapters in ../adapters implement them."""

from .doc_store import DocumentStore
from .publisher import Publisher

__all__ = ["DocumentStore", "Publisher"]
