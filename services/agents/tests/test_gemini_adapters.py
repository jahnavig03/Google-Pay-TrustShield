"""gcp-mode adapters with a fake google-genai client (no credentials, no billing)."""

from types import SimpleNamespace

import pytest
from google.genai import errors
from trustshield_contracts import Decision, SafeAction, Signal

from trustshield_agents.adapters.gemini_caller import GeminiCaller, GeminiUnavailable
from trustshield_agents.adapters.gemini_message_writer import GeminiMessageWriter
from trustshield_agents.adapters.gemini_scam_classifier import GeminiScamClassifier
from trustshield_agents.adapters.rule_scam_classifier import RuleScamClassifier
from trustshield_agents.adapters.template_message_writer import TemplateMessageWriter
from trustshield_agents.ports import MessageInputs, ScamAssessment, ScamPattern


def api_error(code: int) -> errors.APIError:
    cls = errors.ClientError if code < 500 else errors.ServerError
    return cls(code, {"error": {"code": code, "message": "x", "status": "RESOURCE_EXHAUSTED"}})


class FakeClient:
    """Returns / raises the scripted outcomes in order; records every call."""

    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.calls = []

        async def generate_content(**kwargs):
            self.calls.append(kwargs)
            outcome = self.outcomes.pop(0) if len(self.outcomes) > 1 else self.outcomes[0]
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

        self.aio = SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))


def caller(*endpoints, **kw) -> GeminiCaller:
    kw.setdefault("max_qps", 0)  # no pacing unless a test asks for it
    kw.setdefault("backoff_base_ms", 1)
    return GeminiCaller(list(endpoints), "model-from-env", **kw)


GOOD = ScamAssessment(
    scam_probability=0.91,
    pattern=ScamPattern.FAKE_KYC,
    manipulation_cues=["kyc_request"],
    safe_next_step="Check your KYC status in your bank's official app.",
)
OK = SimpleNamespace(parsed=GOOD, text=GOOD.model_dump_json())


# ---- GeminiCaller: retry, fallback location, budget ----


async def test_retries_429_on_fallback_location():
    regional, global_ = FakeClient(api_error(429)), FakeClient(OK)
    c = caller(("asia-south1", regional), ("global", global_))
    assert await c.generate("hi", None) is OK
    assert len(regional.calls) == 1 and len(global_.calls) == 1
    assert c.stats.retries == 1 and c.stats.rate_limited_responses == 1
    assert c.stats.fallback_location_used == 1 and c.stats.succeeded == 1


async def test_non_retryable_error_raises_immediately():
    regional = FakeClient(api_error(404))
    c = caller(("asia-south1", regional), ("global", FakeClient(OK)))
    with pytest.raises(errors.APIError):
        await c.generate("hi", None)
    assert len(regional.calls) == 1 and c.stats.retries == 0


async def test_gives_up_after_max_attempts():
    regional, global_ = FakeClient(api_error(429)), FakeClient(api_error(503))
    c = caller(("asia-south1", regional), ("global", global_), max_attempts=3)
    with pytest.raises(GeminiUnavailable):
        await c.generate("hi", None)
    assert len(regional.calls) == 2 and len(global_.calls) == 1
    assert c.stats.gave_up == 1


async def test_local_pacing_refuses_when_no_slot_in_budget():
    c = caller(("asia-south1", FakeClient(OK)), max_qps=0.1, budget_ms=1000)
    await c.generate("first", None)  # takes the slot; the next one is 10 s away
    with pytest.raises(GeminiUnavailable, match="rate limit"):
        await c.generate("second", None)


# ---- Scam Context adapter ----


async def test_scam_classifier_uses_structured_output():
    client = FakeClient(OK)
    clf = GeminiScamClassifier(caller(("asia-south1", client)), RuleScamClassifier())
    assert await clf.classify("pay to update kyc") == GOOD
    call = client.calls[0]
    assert call["model"] == "model-from-env"
    assert call["config"].response_schema is ScamAssessment
    assert "pay to update kyc" in call["contents"]


async def test_scam_classifier_falls_back_to_rules_when_gemini_is_busy():
    busy = caller(("asia-south1", FakeClient(api_error(429))), max_attempts=2)
    clf = GeminiScamClassifier(busy, RuleScamClassifier())
    result = await clf.classify("Your account will be blocked today, pay immediately")
    assert result.pattern is ScamPattern.URGENCY


async def test_cache_reuses_verdict_for_identical_message():
    client = FakeClient(OK)
    c = caller(("asia-south1", client))
    clf = GeminiScamClassifier(c, RuleScamClassifier(), cache_ttl_s=60)
    await clf.classify("same text")
    await clf.classify("same text")
    await clf.classify("different text")
    assert len(client.calls) == 2 and c.stats.cache_hits == 1


# ---- customer message adapter ----


def _inputs(decision=Decision.HOLD_AND_ESCALATE):
    return MessageInputs(
        decision=decision,
        risk_type="urgency",
        signals=[
            Signal(
                code="new_beneficiary",
                label="New recipient",
                plain_explanation="The recipient was added 4 minutes ago.",
                contribution=2.2,
            )
        ],
        safe_actions=[SafeAction(code="cancel_payment", label="Cancel this payment")],
        safe_next_step="Pause.",
        citations=[],
    )


async def test_message_writer_rejects_credential_requests():
    bad = SimpleNamespace(text="Please share your OTP so we can verify this payment.")
    writer = GeminiMessageWriter(caller(("r", FakeClient(bad))), TemplateMessageWriter())
    text = await writer.write(_inputs())
    assert "OTP" not in text and text.startswith("We've paused this payment")


async def test_message_writer_returns_clean_llm_text():
    ok = SimpleNamespace(text="We've paused this payment so you can check the recipient first.")
    client = FakeClient(ok)
    writer = GeminiMessageWriter(caller(("r", client)), TemplateMessageWriter())
    assert await writer.write(_inputs()) == ok.text
    assert "The recipient was added 4 minutes ago." in client.calls[0]["contents"]


async def test_message_writer_skips_llm_on_allow():
    client = FakeClient(SimpleNamespace(text="unused"))
    writer = GeminiMessageWriter(caller(("r", client)), TemplateMessageWriter())
    await writer.write(_inputs(Decision.ALLOW))
    assert client.calls == []
