"""Every demo fixture must validate against the contract models."""

import pytest
from pydantic import BaseModel

from trustshield_contracts import (
    AnalystDecisionRequest,
    AuditRecord,
    Case,
    CaseAnswer,
    CaseDecisionResponse,
    CaseListResponse,
    CaseQuestion,
    Decision,
    MerchantVerifyRequest,
    MerchantVerifyResponse,
    PaymentRiskRequest,
    PaymentRiskResponse,
    PaymentStatus,
)
from trustshield_contracts.fixtures import (
    DEMO1_PAYMENT,
    DEMO2_CASE,
    DEMO3_SCREENSHOT,
    fixtures_dir,
    load_fixture,
)

SCHEMA: dict[str, dict[str, type[BaseModel]]] = {
    DEMO1_PAYMENT: {"request": PaymentRiskRequest, "expected_response": PaymentRiskResponse},
    DEMO2_CASE: {
        "case": Case,
        "case_list": CaseListResponse,
        "ask_request": CaseQuestion,
        "ask_response": CaseAnswer,
        "decision_request": AnalystDecisionRequest,
        "decision_response": CaseDecisionResponse,
        "audit_record": AuditRecord,
    },
    DEMO3_SCREENSHOT: {
        "request": MerchantVerifyRequest,
        "expected_response": MerchantVerifyResponse,
    },
}


def test_every_fixture_file_is_covered():
    on_disk = {p.stem for p in fixtures_dir().glob("*.json")}
    assert on_disk == set(SCHEMA)


@pytest.mark.parametrize(
    ("fixture", "key", "model"),
    [(f, k, m) for f, parts in SCHEMA.items() for k, m in parts.items()],
)
def test_fixture_part_validates(fixture, key, model):
    model.model_validate(load_fixture(fixture)[key])


@pytest.mark.parametrize("fixture", list(SCHEMA))
def test_no_unvalidated_parts(fixture):
    keys = {k for k in load_fixture(fixture) if not k.startswith("_")}
    assert keys == set(SCHEMA[fixture])


def test_demo_story_expectations():
    demo1 = PaymentRiskResponse.model_validate(load_fixture(DEMO1_PAYMENT)["expected_response"])
    assert demo1.decision is Decision.HOLD_AND_ESCALATE
    assert demo1.analyst_case_required and demo1.evidence_ids
    assert 3 <= len(demo1.top_signals) <= 5

    case = Case.model_validate(load_fixture(DEMO2_CASE)["case"])
    assert case.transaction_id == load_fixture(DEMO1_PAYMENT)["request"]["transaction_id"]
    assert {c.evidence_id for c in case.citations} <= set(case.evidence_ids)

    demo3 = MerchantVerifyResponse.model_validate(
        load_fixture(DEMO3_SCREENSHOT)["expected_response"]
    )
    assert demo3.payment_status is PaymentStatus.SUSPICIOUS
