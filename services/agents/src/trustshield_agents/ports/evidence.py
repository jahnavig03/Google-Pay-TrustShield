from __future__ import annotations

from typing import Protocol

from trustshield_contracts import Decision, PolicyCitation


class EvidenceProvider(Protocol):
    """Policy evidence for a decision. Vertex AI Search replaces the static mapping later."""

    def evidence_ids(self, risk_type: str, decision: Decision) -> list[str]: ...

    def citations(self, evidence_ids: list[str]) -> list[PolicyCitation]: ...
