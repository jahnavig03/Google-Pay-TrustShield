"""Investigator: policy citations for a case, and grounded Q&A over it.

Retrieval is a keyword search (BM25) over the synthetic policy passages in
data/policies/corpus.yaml; titles and URIs come from the evidence catalog (config/evidence.yaml).
It is free, deterministic and runs the same in mock and gcp mode.

Grounding rules:
- every policy claim in an answer quotes a retrieved passage and cites its evidence ID;
- if no passage scores at least ``min_score``, the answer is exactly "not covered by policy".

"Why was this flagged?" questions are answered from the case's own signals, plus the lead
passage of each policy the risk decision cited.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel
from trustshield_contracts import NOT_COVERED_BY_POLICY, Case, CaseAnswer, Decision, PolicyCitation

from .adapters.static_evidence import StaticEvidenceProvider
from .paths import agents_home, config_dir

_K1 = 1.2
_B = 0.75
_STOPWORDS = {
    "a", "about", "an", "and", "any", "are", "as", "at", "be", "can", "case", "could", "do",
    "does", "for", "from", "has", "have", "how", "i", "if", "in", "is", "it", "its", "me", "my",
    "of", "on", "or", "our", "policy", "policies", "say", "says", "should", "tell", "that", "the",
    "their", "there", "this", "to", "us", "was", "we", "were", "what", "when", "where", "which",
    "who", "will", "with", "would", "you", "your",
}  # fmt: skip
_WHY = re.compile(r"\b(why|reason|reasons)\b", re.IGNORECASE)
_FLAG_WORDS = re.compile(
    r"\b(flag\w*|held|hold\w*|paus\w*|block\w*|escalat\w*|scor\w*|risk\w*)", re.IGNORECASE
)


class InvestigatorConfig(BaseModel):
    min_score: float
    min_coverage: float
    case_boost: float
    relative_cutoff: float
    max_citations: int


class Passage(BaseModel):
    evidence_id: str
    text: str
    lead: bool


def _stem(token: str) -> str:
    for suffix in ("ing", "ed", "es", "s"):
        if len(token) > len(suffix) + 3 and token.endswith(suffix):
            return token[: -len(suffix)]
    return token


def tokens(text: str) -> list[str]:
    words = re.findall(r"[a-z0-9]+", text.lower())
    return [_stem(w) for w in words if w not in _STOPWORDS and len(w) > 1]


class PolicyIndex:
    """BM25 over passages. Each passage is indexed with its policy title, so 'KYC' finds §1."""

    def __init__(
        self, corpus_path: Path | None = None, evidence: StaticEvidenceProvider | None = None
    ):
        self.evidence = evidence or StaticEvidenceProvider()
        raw = yaml.safe_load(
            (corpus_path or agents_home() / "data" / "policies" / "corpus.yaml").read_text(
                encoding="utf-8"
            )
        )
        self.passages: list[Passage] = []
        self._docs: list[Counter[str]] = []
        for evidence_id, texts in raw.items():
            [catalog] = self.evidence.citations([evidence_id]) or [None]
            title = catalog.title if catalog else ""
            for i, text in enumerate(texts):
                self.passages.append(Passage(evidence_id=evidence_id, text=text, lead=i == 0))
                self._docs.append(Counter(tokens(f"{title} {text}")))
        self._avg_len = sum(sum(d.values()) for d in self._docs) / max(1, len(self._docs))
        df: Counter[str] = Counter()
        for doc in self._docs:
            df.update(doc.keys())
        n = len(self._docs)
        self._idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def coverage(self, query: list[str], i: int) -> float:
        terms = set(query)
        return sum(1 for t in terms if t in self._docs[i]) / len(terms) if terms else 0.0

    def score(self, query: list[str], i: int) -> float:
        doc = self._docs[i]
        length = sum(doc.values())
        total = 0.0
        for term in set(query):
            tf = doc.get(term, 0)
            if tf:
                norm = tf + _K1 * (1 - _B + _B * length / self._avg_len)
                total += self._idf[term] * tf * (_K1 + 1) / norm
        return total

    def search(self, question: str, boost_ids: set[str], cfg: InvestigatorConfig) -> list[Passage]:
        """Best passage per policy, best policies first, only those scoring >= min_score."""
        query = tokens(question)
        best: dict[str, tuple[float, Passage]] = {}
        for i, passage in enumerate(self.passages):
            s = self.score(query, i)
            if passage.evidence_id in boost_ids:
                s *= cfg.case_boost
            if s < cfg.min_score or self.coverage(query, i) < cfg.min_coverage:
                continue
            if s > best.get(passage.evidence_id, (0.0, passage))[0]:
                best[passage.evidence_id] = (s, passage)
        ranked = sorted(best.values(), key=lambda pair: pair[0], reverse=True)
        if not ranked:
            return []
        top = ranked[0][0]
        kept = [p for s, p in ranked if s >= cfg.relative_cutoff * top]
        return kept[: cfg.max_citations]

    def lead(self, evidence_id: str) -> Passage | None:
        return next((p for p in self.passages if p.evidence_id == evidence_id and p.lead), None)

    def cite(self, passage: Passage) -> PolicyCitation:
        [catalog] = self.evidence.citations([passage.evidence_id])
        return catalog.model_copy(update={"snippet": passage.text})


@lru_cache(maxsize=1)
def _index() -> PolicyIndex:
    return PolicyIndex()


@lru_cache(maxsize=1)
def _config() -> InvestigatorConfig:
    raw = yaml.safe_load((config_dir() / "investigator.yaml").read_text(encoding="utf-8"))
    return InvestigatorConfig.model_validate(raw)


def policy_citations(evidence_ids: list[str]) -> list[PolicyCitation]:
    """Catalog citations for a decision's evidence IDs (what a new case shows under Evidence)."""
    return _index().evidence.citations(evidence_ids)


def _why_answer(case: Case, index: PolicyIndex) -> CaseAnswer | None:
    """Signals from the case, plus the lead passage of each risk-type policy the case cites."""
    if not case.top_signals:
        return None
    signals = "; ".join(
        f"{s.label} ({s.plain_explanation.rstrip('.')})" for s in case.top_signals[:4]
    )
    risk_type_ids = set(index.evidence.evidence_ids(case.risk_type, Decision.ALLOW))
    cited = [eid for eid in case.evidence_ids if eid in risk_type_ids] or case.evidence_ids
    passages = [p for eid in cited[: _config().max_citations] if (p := index.lead(eid))]
    answer = f"R = {case.risk_score:.3f} ({case.decision.value}). Signals: {signals}."
    if passages:
        answer += " " + " ".join(f"Policy: {p.text} [{p.evidence_id}]" for p in passages)
    return CaseAnswer(answer=answer, citations=[index.cite(p) for p in passages])


def answer_case_question(case: Case, question: str) -> CaseAnswer:
    """Grounded answer to an analyst's question about ``case``."""
    index, cfg = _index(), _config()
    if _WHY.search(question) and _FLAG_WORDS.search(question):
        why = _why_answer(case, index)
        if why is not None:
            return why
    passages = index.search(question, set(case.evidence_ids), cfg)
    if not passages:
        return CaseAnswer(answer=NOT_COVERED_BY_POLICY, citations=[])
    answer = " ".join(f"{p.text} [{p.evidence_id}]" for p in passages)
    return CaseAnswer(answer=answer, citations=[index.cite(p) for p in passages])
