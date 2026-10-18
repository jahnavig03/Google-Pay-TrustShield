"""Investigator: policy citations and grounded case Q&A (keyword search, no credentials)."""

from __future__ import annotations

import pytest
import yaml
from trustshield_contracts import NOT_COVERED_BY_POLICY, Case
from trustshield_contracts.fixtures import load_fixture

from trustshield_agents import answer_case_question, policy_citations
from trustshield_agents.adapters.static_evidence import StaticEvidenceProvider
from trustshield_agents.paths import agents_home

CASE = Case.model_validate(load_fixture("demo2_analyst_case")["case"])


def test_every_corpus_policy_is_in_the_evidence_catalog_and_vice_versa():
    corpus = yaml.safe_load((agents_home() / "data/policies/corpus.yaml").read_text("utf-8"))
    catalog = yaml.safe_load((agents_home() / "config/evidence.yaml").read_text("utf-8"))
    assert set(corpus) == set(catalog["catalog"])
    for evidence_id, passages in corpus.items():
        assert passages, evidence_id
        # The lead passage is the catalog snippet, so a case's citation and its answer agree.
        assert passages[0] == catalog["catalog"][evidence_id]["snippet"]


def test_policy_citations_follow_the_evidence_ids():
    ids = ["policy_kyc_03", "policy_escalation_04", "policy_unknown_99"]
    assert [c.evidence_id for c in policy_citations(ids)] == ids[:2]


def test_why_question_answers_from_signals_and_cites_the_risk_type_policies():
    answer = answer_case_question(CASE, "Why was this payment flagged?")
    assert [c.evidence_id for c in answer.citations] == [
        "policy_payment_safety_01",
        "policy_kyc_03",
    ]
    assert CASE.top_signals[0].label in answer.answer
    for citation in answer.citations:
        assert f"[{citation.evidence_id}]" in answer.answer
        assert citation.snippet in answer.answer


@pytest.mark.parametrize(
    ("question", "evidence_id"),
    [
        ("What does policy say about KYC update requests?", "policy_kyc_03"),
        ("Can a hold be executed without analyst approval?", "policy_escalation_04"),
        ("Is a payment screenshot proof of payment?", "policy_merchant_05"),
        ("Does receiving money need a PIN?", "policy_collect_07"),
        ("How do QR sticker swaps work?", "policy_qr_08"),
        ("Tell me about mule accounts", "policy_mule_09"),
        ("What is the refund policy?", "policy_refund_06"),
    ],
)
def test_policy_questions_cite_the_matching_passage(question, evidence_id):
    answer = answer_case_question(CASE, question)
    assert answer.citations[0].evidence_id == evidence_id
    assert all(f"[{c.evidence_id}]" in answer.answer for c in answer.citations)
    assert all(c.snippet in answer.answer for c in answer.citations)


@pytest.mark.parametrize(
    "question",
    ["What is the weather in Mumbai?", "Who won the cricket match?", "Why is the sky blue?"],
)
def test_nothing_retrieved_is_exactly_not_covered_by_policy(question):
    answer = answer_case_question(CASE, question)
    assert answer.answer == NOT_COVERED_BY_POLICY
    assert answer.citations == []


def test_snippet_is_the_passage_that_was_retrieved_not_the_catalog_summary():
    answer = answer_case_question(CASE, "Can the customer be asked for an OTP?")
    [catalog] = StaticEvidenceProvider().citations(["policy_kyc_03"])
    assert answer.citations[0].evidence_id == "policy_kyc_03"
    assert "OTP" in answer.citations[0].snippet
    assert answer.citations[0].title == catalog.title
