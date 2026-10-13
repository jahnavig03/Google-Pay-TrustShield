"""Identifier formats for audit rows, cases and approval records."""

from __future__ import annotations

import uuid


def _suffix(length: int = 12) -> str:
    return uuid.uuid4().hex[:length].upper()


def new_audit_id() -> str:
    return f"AUD-{_suffix()}"


def new_approval_id() -> str:
    return f"APPR-{_suffix()}"


def case_id_for(transaction_id: str) -> str:
    """One case per transaction, so a retried evaluation reuses the same case."""
    return f"CASE-{transaction_id}"
