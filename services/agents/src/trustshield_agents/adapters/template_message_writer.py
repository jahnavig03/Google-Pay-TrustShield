"""Deterministic customer-message templates (mock mode; also the Gemini fallback)."""

from __future__ import annotations

from trustshield_contracts import Decision

from ..ports.message_writer import MessageInputs

_PATTERN_SENTENCE = {
    "urgency": "It has signs we often see in messages that create urgency, such as a warning "
    "that an account will be blocked.",
    "fake_kyc": "It has signs we often see in requests to pay for a KYC update.",
    "fake_refund": "It has signs we often see in refund offers that ask you to pay first.",
    "receive_money_first": "It looks like a request that takes money from your account, "
    "even though the message talks about receiving money.",
    "impersonation": "The message claims to come from an official source, which we "
    "couldn't confirm.",
    "qr_swap": "The QR code may not belong to the person or shop you intend to pay.",
    "mule_network": "The recipient's account has some unusual recent activity.",
}


def _first_policy_sentence(inputs: MessageInputs) -> str:
    # Only paraphrase policy we actually retrieved (evidence-backed).
    ids = {c.evidence_id for c in inputs.citations}
    if "policy_kyc_03" in ids and inputs.risk_type in ("urgency", "fake_kyc"):
        return "Banks never ask you to transfer money to keep an account active or to update KYC."
    if "policy_collect_07" in ids:
        return "You never need to pay or approve a request to receive money."
    if "policy_refund_06" in ids:
        return "Genuine refunds don't require you to pay or approve anything."
    return ""


class TemplateMessageWriter:
    name = "template"

    async def write(self, inputs: MessageInputs) -> str:
        top = inputs.signals[0].plain_explanation if inputs.signals else ""
        pattern = _PATTERN_SENTENCE.get(inputs.risk_type, top)
        policy = _first_policy_sentence(inputs)

        if inputs.decision is Decision.ALLOW:
            return "This payment looks fine. You can go ahead."
        if inputs.decision is Decision.WARN:
            parts = [
                "Please take a moment before you pay.",
                top or pattern,
                (
                    "If you're not sure, check the recipient's details with them directly "
                    "before continuing."
                ),
            ]
        elif inputs.decision is Decision.STEP_UP_VERIFICATION:
            parts = [
                "We'd like you to confirm a few details before this payment goes through.",
                pattern,
                policy,
                (
                    "Please verify the recipient through a contact you already trust, "
                    "or cancel the payment."
                ),
            ]
        else:
            parts = [
                "We've paused this payment so you can check it first.",
                pattern,
                policy,
                (
                    "Please don't proceed until you've verified the request through your "
                    "bank's official app or helpline."
                ),
            ]
        return " ".join(p for p in parts if p)
