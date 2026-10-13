"""Customer message from Gemini using prompts/customer_message.<v>.md (gcp mode)."""

from __future__ import annotations

import logging

from google.genai import types
from trustshield_contracts import Decision

from ..guardrails import customer_text_violations
from ..ports.message_writer import MessageInputs
from ..prompts import load_prompt
from .gemini_caller import GeminiCaller
from .template_message_writer import TemplateMessageWriter

log = logging.getLogger(__name__)


class GeminiMessageWriter:
    name = "gemini"

    def __init__(
        self,
        caller: GeminiCaller,
        fallback: TemplateMessageWriter,
        thinking: types.ThinkingConfig | None = None,
    ):
        self.caller = caller
        self._fallback = fallback
        self._thinking = thinking
        self._template = load_prompt("customer_message")

    def _render(self, inputs: MessageInputs) -> str:
        return self._template.format(
            decision=inputs.decision.value,
            signals="\n".join(f"- {s.plain_explanation}" for s in inputs.signals),
            safe_next_step=inputs.safe_next_step,
            safe_actions="\n".join(f"- {a.label}" for a in inputs.safe_actions),
            evidence="\n".join(f"- {c.snippet}" for c in inputs.citations) or "- (none)",
        )

    async def write(self, inputs: MessageInputs) -> str:
        if inputs.decision is Decision.ALLOW:  # keep the happy path fast: no LLM call
            return await self._fallback.write(inputs)
        try:
            resp = await self.caller.generate(
                contents=self._render(inputs),
                config=types.GenerateContentConfig(
                    temperature=0.2, max_output_tokens=512, thinking_config=self._thinking
                ),
            )
            text = (resp.text or "").strip()
            problems = customer_text_violations(text)
            if not problems:
                return text
            log.warning("Gemini customer message rejected by guardrails: %s", problems)
        except Exception as exc:  # noqa: BLE001 — never fail the payment path on the LLM
            log.warning("Gemini customer message failed, using template: %s", str(exc)[:300])
        return await self._fallback.write(inputs)
