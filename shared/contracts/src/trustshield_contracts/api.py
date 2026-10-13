"""Endpoint registry: method, path and models for every /api/v1 route.

The gateway implements these; scripts/export_openapi.py turns them into openapi.json.
"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel

from .cases import (
    AnalystDecisionRequest,
    Case,
    CaseAnswer,
    CaseDecisionResponse,
    CaseListResponse,
    CaseQuestion,
)
from .merchant import MerchantVerifyRequest, MerchantVerifyResponse
from .payment import PaymentRiskRequest, PaymentRiskResponse

API_PREFIX = "/api/v1"


@dataclass(frozen=True)
class Endpoint:
    method: str
    path: str
    operation_id: str
    summary: str
    tag: str
    response_model: type[BaseModel]
    request_model: type[BaseModel] | None = None


ENDPOINTS: tuple[Endpoint, ...] = (
    Endpoint(
        "POST",
        f"{API_PREFIX}/payment-risk/evaluate",
        "evaluatePaymentRisk",
        "Score a payment and return allow / warn / step-up / hold",
        "paysafe",
        PaymentRiskResponse,
        PaymentRiskRequest,
    ),
    Endpoint(
        "POST",
        f"{API_PREFIX}/merchant/payment-verify",
        "verifyMerchantPayment",
        "Check a payment screenshot against the merchant ledger",
        "payguard",
        MerchantVerifyResponse,
        MerchantVerifyRequest,
    ),
    Endpoint(
        "GET",
        f"{API_PREFIX}/cases",
        "listCases",
        "List analyst cases",
        "investigator",
        CaseListResponse,
    ),
    Endpoint(
        "GET",
        f"{API_PREFIX}/cases/{{case_id}}",
        "getCase",
        "Get one case with timeline, links and citations",
        "investigator",
        Case,
    ),
    Endpoint(
        "POST",
        f"{API_PREFIX}/cases/{{case_id}}/ask",
        "askCase",
        "Grounded Q&A over a case",
        "investigator",
        CaseAnswer,
        CaseQuestion,
    ),
    Endpoint(
        "POST",
        f"{API_PREFIX}/cases/{{case_id}}/decision",
        "decideCase",
        "Record the analyst's decision (human approval)",
        "investigator",
        CaseDecisionResponse,
        AnalystDecisionRequest,
    ),
)
