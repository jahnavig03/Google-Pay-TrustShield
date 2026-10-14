"""PayGuard: verify_merchant_payment against the mock screenshots + ledger (no credentials)."""

import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from google.genai import types
from trustshield_contracts import MerchantVerifyRequest, PaymentStatus, RiskLevel
from trustshield_contracts.fixtures import load_fixture

import trustshield_agents
from trustshield_agents.guardrails import customer_text_violations
from trustshield_agents.merchant import (
    build_merchant_services,
    verify_merchant_payment,
    verify_with,
)
from trustshield_agents.merchant.extractors import (
    GeminiScreenshotExtractor,
    MockScreenshotExtractor,
    ScreenshotReading,
)
from trustshield_agents.merchant.ledgers import (
    BigQueryMerchantLedger,
    FallbackLedger,
    JsonMerchantLedger,
)
from trustshield_agents.merchant.models import Extraction, LedgerEntry, TamperHint, load_rules
from trustshield_agents.merchant.rules import decide
from trustshield_agents.merchant.service import MerchantServices
from trustshield_agents.paths import mock_data_dir

DEMO3 = load_fixture("demo3_fake_screenshot_12k")
SHOTS = json.loads((mock_data_dir() / "screenshots.json").read_text(encoding="utf-8"))[
    "screenshots"
]
FLAGGED = {
    PaymentStatus.SUSPICIOUS,
    PaymentStatus.INCONSISTENT,
    PaymentStatus.NOT_FOUND_IN_LEDGER,
}


def request_for(uri: str) -> MerchantVerifyRequest:
    case = SHOTS[uri]["_case"]
    return MerchantVerifyRequest(
        merchant_id=case["merchant_id"],
        uploaded_screenshot=uri,
        claimed_amount=case["claimed_amount"],
        claimed_transaction_id=case["claimed_transaction_id"],
    )


def uris_of(kind: str) -> list[str]:
    return [u for u, s in SHOTS.items() if s["_case"]["kind"] == kind]


@pytest.fixture
def services():
    return build_merchant_services("mock")


# ---- demo 3 -----------------------------------------------------------------------------


async def test_demo3_fake_screenshot_is_suspicious_high():
    resp = await verify_merchant_payment(MerchantVerifyRequest.model_validate(DEMO3["request"]))
    expected = DEMO3["expected_response"]
    assert resp.payment_status == PaymentStatus.SUSPICIOUS
    assert resp.risk_level == RiskLevel.HIGH
    assert resp.audit_id is None  # the gateway's Governance fills it in
    assert resp.extracted.amount == expected["extracted"]["amount"]
    assert resp.extracted.txn_id == expected["extracted"]["txn_id"]
    assert resp.extracted.vpa == expected["extracted"]["vpa"]
    assert resp.extracted.timestamp == datetime.fromisoformat(expected["extracted"]["timestamp"])
    assert resp.explanation == expected["explanation"]
    assert resp.recommended_action == expected["recommended_action"]


async def test_exported_like_evaluate_payment():
    assert "verify_merchant_payment" in trustshield_agents.__all__
    assert trustshield_agents.verify_merchant_payment is verify_merchant_payment


# ---- one test per status ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("kind", "status", "risk"),
    [
        ("genuine_settled", PaymentStatus.VERIFIED, RiskLevel.LOW),
        ("genuine_pending", PaymentStatus.PENDING, RiskLevel.MEDIUM),
        ("edited_amount", PaymentStatus.INCONSISTENT, RiskLevel.HIGH),
        ("edited_vpa", PaymentStatus.INCONSISTENT, RiskLevel.MEDIUM),
        ("reused_old_screenshot", PaymentStatus.INCONSISTENT, RiskLevel.MEDIUM),
        ("fake_clean", PaymentStatus.NOT_FOUND_IN_LEDGER, RiskLevel.MEDIUM),
        ("fake_tampered", PaymentStatus.SUSPICIOUS, RiskLevel.HIGH),
    ],
)
async def test_every_status(services, kind, status, risk):
    uris = uris_of(kind)
    assert uris, kind
    for uri in uris:
        resp = await verify_with(request_for(uri), services)
        assert (resp.payment_status, resp.risk_level) == (status, risk), (uri, resp.explanation)


async def test_detection_rate_meets_the_prd_target(services):
    """PRD §2: merchant screenshot-fraud detection ≥ 90% on synthetic cases (20+ screenshots)."""
    assert len(SHOTS) >= 20
    fakes = genuine = caught = false_alarms = 0
    for uri, shot in SHOTS.items():
        resp = await verify_with(request_for(uri), services)
        assert resp.payment_status.value == shot["_case"]["expected_status"], uri
        if shot["_case"]["is_fake"]:
            fakes += 1
            caught += resp.payment_status in FLAGGED
        else:
            genuine += 1
            false_alarms += resp.payment_status in FLAGGED
    assert fakes >= 15 and genuine >= 10
    assert caught / fakes >= 0.90
    assert false_alarms == 0


async def test_merchant_text_is_neutral_and_never_asks_for_credentials(services):
    for uri in SHOTS:
        resp = await verify_with(request_for(uri), services)
        text = f"{resp.explanation} {resp.recommended_action}"
        assert customer_text_violations(text) == [], (uri, text)
        assert "fraud" not in text.lower() and "scam" not in text.lower()


# ---- rules in isolation -------------------------------------------------------------------

NOW = datetime(2026, 10, 13, 15, 0, tzinfo=UTC)
ENTRY = LedgerEntry(
    merchant_id="MER-T",
    merchant_vpa="mer.test.0001@synthbank",
    entry_type="credit",
    txn_id="111122223333",
    amount=500.0,
    counterparty_vpa="a.b.00001@synthbank",
    initiated_at=NOW - timedelta(minutes=5),
    settled_at=NOW - timedelta(minutes=4),
    status="settled",
)
REQ = MerchantVerifyRequest(
    merchant_id="MER-T",
    uploaded_screenshot="gs://x/y.png",
    claimed_amount=500,
    claimed_transaction_id="111122223333",
)


def run(ex: Extraction, entry=ENTRY, req=REQ):
    return decide(req, ex, entry, load_rules(), NOW)


def test_unreadable_screenshot_falls_back_to_the_ledger():
    assert run(Extraction()).payment_status == PaymentStatus.VERIFIED
    assert run(Extraction(), entry=None).payment_status == PaymentStatus.NOT_FOUND_IN_LEDGER


def test_future_timestamp_alone_makes_a_missing_payment_suspicious():
    ex = Extraction(timestamp=NOW + timedelta(minutes=10), shown_at=NOW)
    resp = run(ex, entry=None)
    assert resp.payment_status == PaymentStatus.SUSPICIOUS
    assert "10 minutes after the time it was shown" in resp.explanation


def test_ledger_wins_over_tamper_hints_when_the_money_has_settled():
    ex = Extraction(amount=500, tamper_hints=[TamperHint.FONT_MISMATCH])
    assert run(ex).payment_status == PaymentStatus.VERIFIED


def test_refund_entry_is_not_a_received_payment():
    resp = run(Extraction(), entry=ENTRY.model_copy(update={"entry_type": "refund"}))
    assert (resp.payment_status, resp.risk_level) == (PaymentStatus.INCONSISTENT, RiskLevel.HIGH)


def test_time_mismatch_is_inconsistent():
    ex = Extraction(timestamp=ENTRY.initiated_at - timedelta(hours=2), shown_at=NOW)
    assert run(ex).payment_status == PaymentStatus.INCONSISTENT


async def test_lookup_retries_with_the_txn_id_read_off_the_screenshot():
    """A typo in the claimed id still finds the payment the screenshot shows."""

    class OneEntry:
        name = "one"

        async def find(self, merchant_id, txn_id):
            return ENTRY if txn_id == ENTRY.txn_id else None

    class Reads:
        name = "reads"

        async def extract(self, uri):
            return Extraction(amount=500, txn_id=ENTRY.txn_id, vpa=ENTRY.merchant_vpa)

    req = REQ.model_copy(update={"claimed_transaction_id": "999999999999"})
    resp = await verify_with(req, MerchantServices(Reads(), OneEntry(), load_rules()), now=NOW)
    assert resp.payment_status == PaymentStatus.VERIFIED


# ---- adapters -------------------------------------------------------------------------------


async def test_mock_ledger_matches_the_demo_story():
    ledger = JsonMerchantLedger()
    assert await ledger.find("MER-DEMO-0042", "428913570012") is None
    known = next(u for u in uris_of("genuine_settled"))
    case = SHOTS[known]["_case"]
    entry = await ledger.find(case["merchant_id"], case["claimed_transaction_id"])
    assert entry is not None and entry.status == "settled"


async def test_unknown_screenshot_is_unreadable_not_an_error():
    ex = await MockScreenshotExtractor().extract("gs://nowhere/never-seen.png")
    assert ex == Extraction()


class FakeCaller:
    def __init__(self, outcome):
        self.outcome, self.calls = outcome, []

    async def generate(self, contents, config):
        self.calls.append((contents, config))
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


async def test_gemini_extractor_parses_the_json_schema():
    reading = ScreenshotReading(
        amount=12000,
        txn_id=" 428913570012 ",
        vpa="Mer.Demo0042@synthbank",
        timestamp="2026-10-13T14:22:00",
        tamper_hints=["font_mismatch", "future_timestamp", "made_up"],
    )
    caller = FakeCaller(SimpleNamespace(parsed=reading, text=reading.model_dump_json()))
    ex = await GeminiScreenshotExtractor(caller, MockScreenshotExtractor()).extract("gs://b/x.png")
    assert ex.source == "gemini"
    assert (ex.amount, ex.txn_id, ex.vpa) == (12000, "428913570012", "mer.demo0042@synthbank")
    assert ex.timestamp == datetime.fromisoformat("2026-10-13T14:22:00+05:30")  # naive -> IST
    assert ex.tamper_hints == [TamperHint.FONT_MISMATCH]  # only visual hints are taken
    contents, config = caller.calls[0]
    assert contents[0].file_data.file_uri == "gs://b/x.png"
    assert config.response_schema is ScreenshotReading and config.temperature == 0.0


async def test_output_cap_leaves_room_for_thinking_tokens():
    """Thinking tokens count against max_output_tokens; without room the JSON is cut off."""
    reading = ScreenshotReading(amount=1)
    caller = FakeCaller(SimpleNamespace(parsed=reading, text=reading.model_dump_json()))
    thinking = types.ThinkingConfig(thinking_budget=2048)
    await GeminiScreenshotExtractor(caller, MockScreenshotExtractor(), thinking).extract("gs://b/x")
    assert caller.calls[0][1].max_output_tokens >= 2048 + 256


async def test_gemini_failure_falls_back_to_the_mock():
    caller = FakeCaller(TimeoutError("budget spent"))
    uri = DEMO3["request"]["uploaded_screenshot"]
    ex = await GeminiScreenshotExtractor(caller, MockScreenshotExtractor()).extract(uri)
    assert ex.source == "mock" and ex.txn_id == "428913570012"


def test_bigquery_ledger_request_is_parameterised_and_parses_rows():
    bq = BigQueryMerchantLedger("proj", "trustshield", "asia-south1")
    body = bq.request_body("MER-1", "1234'; DROP TABLE x")
    assert "@merchant_id" in body["query"] and "@txn_id" in body["query"]
    assert "DROP" not in body["query"]  # values only travel as parameters
    assert body["location"] == "asia-south1" and body["useLegacySql"] is False
    row = {
        "schema": {"fields": [{"name": c} for c in (
            "merchant_id", "merchant_vpa", "entry_type", "txn_id", "amount",
            "counterparty_vpa", "initiated_at", "settled_at", "status")]},
        "rows": [{"f": [{"v": v} for v in (
            "MER-1", "mer.x@synthbank", "credit", "123", "500.0", "a@synthbank",
            str(int(datetime(2026, 10, 13, 9, 0, tzinfo=UTC).timestamp() * 1_000_000)),
            None, "pending")]}],
    }  # fmt: skip
    entry = BigQueryMerchantLedger.parse_response(row)
    assert entry.amount == 500.0 and entry.settled_at is None
    assert entry.initiated_at == datetime(2026, 10, 13, 9, 0, tzinfo=UTC)
    assert BigQueryMerchantLedger.parse_response({"rows": []}) is None


async def test_ledger_error_falls_back_but_not_found_does_not():
    class Broken:
        name = "broken"

        async def find(self, merchant_id, txn_id):
            raise RuntimeError("bigquery down")

    class Empty:
        name = "empty"

        async def find(self, merchant_id, txn_id):
            return None

    fallback = JsonMerchantLedger()
    known = SHOTS[uris_of("genuine_settled")[0]]["_case"]
    args = (known["merchant_id"], known["claimed_transaction_id"])
    assert await FallbackLedger(Broken(), fallback).find(*args) is not None
    assert await FallbackLedger(Empty(), fallback).find(*args) is None
