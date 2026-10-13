"""Static risk_type -> policy evidence mapping from config/evidence.yaml."""

from __future__ import annotations

from pathlib import Path

import yaml
from trustshield_contracts import Decision, PolicyCitation

from ..paths import config_dir


class StaticEvidenceProvider:
    def __init__(self, path: Path | None = None):
        cfg = yaml.safe_load((path or config_dir() / "evidence.yaml").read_text(encoding="utf-8"))
        self._by_risk_type: dict[str, list[str]] = cfg["by_risk_type"]
        self._by_decision: dict[str, list[str]] = cfg.get("by_decision", {})
        self._fallback: list[str] = cfg["fallback"]
        self._catalog = {
            eid: PolicyCitation(evidence_id=eid, **doc) for eid, doc in cfg["catalog"].items()
        }

    def evidence_ids(self, risk_type: str, decision: Decision) -> list[str]:
        ids = list(self._by_risk_type.get(risk_type) or self._fallback)
        for eid in self._by_decision.get(decision.value, []):
            if eid not in ids:
                ids.append(eid)
        return ids

    def citations(self, evidence_ids: list[str]) -> list[PolicyCitation]:
        return [self._catalog[e] for e in evidence_ids if e in self._catalog]
