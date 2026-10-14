"""evals/heldout_messages.jsonl: 100 new labelled messages, same schema as scam_messages.jsonl."""

import json
import re
from pathlib import Path

import pytest

EVALS = Path(__file__).resolve().parents[2] / "evals"
LABELS = {
    "urgency",
    "fake_kyc",
    "fake_refund",
    "receive_money_first",
    "impersonation",
    "qr_swap",
    "none",
}
KEYS = {"id", "lang", "label", "is_scam", "hard_negative", "text"}


def _load(name: str) -> list[dict]:
    lines = (EVALS / name).read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


@pytest.fixture(scope="module")
def heldout():
    return _load("heldout_messages.jsonl")


def test_schema_and_size(heldout):
    assert len(heldout) == 100
    for row in heldout:
        assert set(row) == KEYS
        assert row["lang"] in {"en", "hinglish"}
        assert row["label"] in LABELS
        assert row["is_scam"] == (row["label"] != "none")
        assert row["hard_negative"] == (not row["is_scam"])
        assert len(row["text"]) >= 20
    assert len({r["id"] for r in heldout}) == 100


def test_every_label_and_both_languages_are_covered(heldout):
    assert {r["label"] for r in heldout} == LABELS
    for label in LABELS - {"none"}:
        assert sum(r["label"] == label for r in heldout) >= 10
    hinglish = sum(r["lang"] == "hinglish" for r in heldout)
    assert 25 <= hinglish <= 50


def test_about_a_quarter_are_hard_negatives(heldout):
    share = sum(r["hard_negative"] for r in heldout) / len(heldout)
    assert 0.20 <= share <= 0.30


def test_no_overlap_with_the_existing_eval_set(heldout):
    existing = _load("scam_messages.jsonl")
    assert not {r["id"] for r in heldout} & {r["id"] for r in existing}
    assert not {_norm(r["text"]) for r in heldout} & {_norm(r["text"]) for r in existing}
    assert len({_norm(r["text"]) for r in heldout}) == 100


def test_no_real_identifiers(heldout):
    for row in heldout:
        assert not re.search(r"\d{10}", row["text"].replace(",", "")), row["id"]  # phone numbers
        for domain in re.findall(r"[a-z0-9-]+\.[a-z]{2,}(?=[/\s,.]|$)", row["text"].lower()):
            assert domain.endswith(".example"), (row["id"], domain)
