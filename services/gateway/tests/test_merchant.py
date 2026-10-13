"""PayGuard route. The ledger check itself is still a stub behind one function."""

from __future__ import annotations

from trustshield_contracts.fixtures import load_fixture

from conftest import merchant
from trustshield_gateway import governance
from trustshield_gateway.merchant_service import LEDGER_LOOKUP_EVIDENCE_ID

REQUEST = load_fixture("demo3_fake_screenshot_12k")["request"]


async def test_merchant_verify_returns_the_placeholder_result(client):
    resp = await client.post("/api/v1/merchant/payment-verify", headers=merchant(), json=REQUEST)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["payment_status"] == "not_found_in_ledger"
    assert body["risk_level"] == "medium"
    assert body["audit_id"]
    assert body["recommended_action"] and body["explanation"]


async def test_merchant_text_is_non_accusatory_and_credential_free(client):
    resp = await client.post("/api/v1/merchant/payment-verify", headers=merchant(), json=REQUEST)
    body = resp.json()
    text = f"{body['explanation']} {body['recommended_action']}"
    assert not governance.mentions_sensitive_credentials(text)
    assert "fraud" not in text.lower() and "scammer" not in text.lower()


async def test_merchant_audit_row_cites_the_ledger_lookup(client, memory_app):
    resp = await client.post("/api/v1/merchant/payment-verify", headers=merchant(), json=REQUEST)
    rows = await memory_app.state.services.store.list("audit_log")
    assert len(rows) == 1
    assert rows[0]["audit_id"] == resp.json()["audit_id"]
    assert rows[0]["evidence_ids"] == [LEDGER_LOOKUP_EVIDENCE_ID]
    assert rows[0]["actor_id"] == REQUEST["merchant_id"]


async def test_invalid_merchant_request_is_rejected(client):
    resp = await client.post(
        "/api/v1/merchant/payment-verify", headers=merchant(), json={**REQUEST, "claimed_amount": 0}
    )
    assert resp.status_code == 422
