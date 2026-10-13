import pytest

from trustshield_agents.adapters.rule_scam_classifier import RuleScamClassifier
from trustshield_agents.guardrails import customer_text_violations
from trustshield_agents.ports import ScamPattern

clf = RuleScamClassifier()


@pytest.mark.parametrize(
    ("text", "pattern"),
    [
        (
            "Your SBI account will be blocked today. Pay Rs 5000 immediately to keep it active.",
            ScamPattern.URGENCY,
        ),
        (
            "Dear user your KYC has expired. Pay Rs 10 to verification account to re-verify.",
            ScamPattern.FAKE_KYC,
        ),
        (
            "You were charged twice. To get your refund please approve the collect request.",
            ScamPattern.FAKE_REFUND,
        ),
        (
            "Congrats! You won a lucky draw prize of Rs 25 lakh. Pay processing fee to receive it.",
            ScamPattern.RECEIVE_MONEY_FIRST,
        ),
        ("Bhaiya scan this QR code to receive the payment for the sofa", ScamPattern.QR_SWAP),
        (
            "This is Inspector Sharma from cyber cell. Pay the fine now or face arrest, do not tell anyone.",
            ScamPattern.IMPERSONATION,
        ),
        ("Aapka khata band ho jayega, abhi ke abhi 2000 bhejo", ScamPattern.URGENCY),
    ],
)
def test_patterns(text, pattern):
    result = clf.classify_sync(text)
    assert result.pattern is pattern
    assert result.scam_probability >= 0.5


@pytest.mark.parametrize(
    "text",
    [
        None,
        "",
        "Hi! Splitting last night's dinner, your share is 650.",
        "School fee of Rs 15,000 is due today. Please pay via the school app.",
        "Electricity bill due on 20 Oct.",
    ],
)
def test_legitimate_messages_stay_low(text):
    result = clf.classify_sync(text)
    assert result.pattern is ScamPattern.NONE
    assert result.scam_probability < 0.5


def test_safe_next_steps_never_mention_credentials():
    for step in clf._safe_steps.values():
        assert customer_text_violations(step) == []
