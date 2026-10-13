"""Deterministic keyword / regex Scam Context classifier (mock mode; also the Gemini fallback)."""

from __future__ import annotations

import math
import re
from pathlib import Path

import yaml

from ..paths import config_dir
from ..ports.scam_classifier import ScamAssessment, ScamPattern


class RuleScamClassifier:
    name = "rules"

    def __init__(self, path: Path | None = None):
        cfg = yaml.safe_load((path or config_dir() / "scam_rules.yaml").read_text(encoding="utf-8"))
        self._rate = float(cfg["rate"])
        self._cap = float(cfg["cap"])
        self._floor = float(cfg["floor"])
        self._priority = [ScamPattern(p) for p in cfg["pattern_priority"]]
        self._safe_steps = {ScamPattern(k): v for k, v in cfg["safe_next_step"].items()}
        self._rules = [
            (
                re.compile(r["regex"], re.IGNORECASE),
                ScamPattern(r["pattern"]) if r.get("pattern") else None,
                float(r["weight"]),
                r["cue"],
            )
            for r in cfg["rules"]
        ]

    def classify_sync(self, text: str | None) -> ScamAssessment:
        text = (text or "").strip()
        per_pattern: dict[ScamPattern, float] = {}
        cues: list[str] = []
        total = 0.0
        for regex, pattern, weight, cue in self._rules:
            if text and regex.search(text):
                total += weight
                if cue not in cues:
                    cues.append(cue)
                if pattern is not None:
                    per_pattern[pattern] = per_pattern.get(pattern, 0.0) + weight

        probability = max(self._floor, min(self._cap, 1.0 - math.exp(-self._rate * total)))
        pattern = ScamPattern.NONE
        if per_pattern and probability >= 0.5:
            best = max(per_pattern.values())
            pattern = next(p for p in self._priority if per_pattern.get(p) == best)
        return ScamAssessment(
            scam_probability=round(probability, 4),
            pattern=pattern,
            manipulation_cues=cues,
            safe_next_step=self._safe_steps[pattern],
        )

    async def classify(self, text: str) -> ScamAssessment:
        return self.classify_sync(text)
