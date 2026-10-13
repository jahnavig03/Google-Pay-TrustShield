import pytest

from trustshield_agents.guardrails import customer_text_violations


@pytest.mark.parametrize(
    "text",
    [
        "Please share the OTP you received.",
        "Enter your UPI PIN to continue.",
        "Tell us your card number and CVV.",
        "Confirm your password.",
    ],
)
def test_credential_requests_flagged(text):
    assert "mentions_sensitive_credentials" in customer_text_violations(text)


def test_accusatory_flagged():
    assert "accusatory" in customer_text_violations("The recipient is a fraudster.")


def test_clean_text_passes():
    assert customer_text_violations("We've paused this payment so you can check it first.") == []
