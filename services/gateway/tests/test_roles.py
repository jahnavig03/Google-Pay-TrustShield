"""X-Demo-Role: customer -> evaluate, analyst -> /cases*, merchant -> /merchant/*."""

from __future__ import annotations

import pytest
from trustshield_contracts.fixtures import load_fixture

from conftest import analyst, customer, merchant

PAYMENT = load_fixture("demo1_payment_85k")["request"]
SCREENSHOT = load_fixture("demo3_fake_screenshot_12k")["request"]


async def test_evaluate_without_a_role_header_is_401(client):
    resp = await client.post("/api/v1/payment-risk/evaluate", json=PAYMENT)
    assert resp.status_code == 401


@pytest.mark.parametrize("headers", [analyst(), merchant()])
async def test_evaluate_needs_the_customer_role(client, headers):
    resp = await client.post("/api/v1/payment-risk/evaluate", headers=headers, json=PAYMENT)
    assert resp.status_code == 403


@pytest.mark.parametrize("headers", [customer(), merchant()])
async def test_cases_need_the_analyst_role(client, headers):
    assert (await client.get("/api/v1/cases", headers=headers)).status_code == 403


async def test_cases_with_the_analyst_role_are_allowed(client):
    assert (await client.get("/api/v1/cases", headers=analyst())).status_code == 200


@pytest.mark.parametrize("headers", [customer(), analyst()])
async def test_merchant_route_needs_the_merchant_role(client, headers):
    resp = await client.post("/api/v1/merchant/payment-verify", headers=headers, json=SCREENSHOT)
    assert resp.status_code == 403
