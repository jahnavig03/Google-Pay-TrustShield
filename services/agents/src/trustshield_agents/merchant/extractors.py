"""Screenshot extraction: a JSON lookup (mock) and Gemini vision (gcp, falls back to the lookup)."""

from __future__ import annotations

import base64
import json
import logging
import mimetypes
from datetime import datetime
from pathlib import Path

from google.genai import types
from pydantic import BaseModel, Field

from ..adapters.gemini_caller import GeminiCaller
from ..paths import mock_data_dir
from ..prompts import load_prompt
from .models import Extraction, TamperHint, as_aware

log = logging.getLogger(__name__)


class MockScreenshotExtractor:
    """Looks the URI up in data/mock/screenshots.json. Unknown URIs read as unreadable."""

    name = "mock"

    def __init__(self, path: Path | None = None):
        data = json.loads(
            (path or mock_data_dir() / "screenshots.json").read_text(encoding="utf-8")
        )
        self._shots: dict[str, dict] = data.get("screenshots", {})

    def known(self, uri: str) -> bool:
        return uri in self._shots

    async def extract(self, uri: str) -> Extraction:
        record = self._shots.get(uri)
        if record is None:
            return Extraction()
        fields = {k: v for k, v in record.items() if not k.startswith("_")}
        return Extraction.model_validate({**fields, "source": "mock"})


# What Gemini returns (response_schema). Visual hints only: the future-timestamp check is done
# in code against the time the screenshot was shown.
_VISUAL_HINTS = [h.value for h in TamperHint if h is not TamperHint.FUTURE_TIMESTAMP]


class ScreenshotReading(BaseModel):
    amount: float | None = Field(None, description="Amount paid in rupees, digits only")
    txn_id: str | None = Field(None, description="UPI transaction / reference id (UTR)")
    vpa: str | None = Field(None, description="The payee's UPI id (VPA) shown on the receipt")
    timestamp: str | None = Field(
        None, description="Payment date and time as ISO 8601, e.g. 2026-10-13T14:22:00+05:30"
    )
    tamper_hints: list[str] = Field(
        default_factory=list, description=f"Any of: {', '.join(_VISUAL_HINTS)}. Empty if none."
    )


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return as_aware(datetime.fromisoformat(value))  # 3.11+ parses a trailing Z
    except ValueError:
        return None


def image_part(uri: str) -> types.Part:
    """gs:// or https:// is read by Vertex AI directly; data: URIs are sent inline."""
    if uri.startswith("data:"):
        header, _, payload = uri.partition(",")
        mime = header[5:].split(";")[0] or "image/png"
        return types.Part.from_bytes(data=base64.b64decode(payload), mime_type=mime)
    mime = mimetypes.guess_type(uri)[0] or "image/png"
    return types.Part.from_uri(file_uri=uri, mime_type=mime)


class GeminiScreenshotExtractor:
    """Gemini (GEMINI_FAST_MODEL) reads the image; JSON response schema, no thinking.

    Any failure (bad URI, timeout, 429s past the budget, unparsable output) falls back to the
    mock lookup, then to "unreadable", so a merchant check never fails because of the LLM.
    """

    name = "gemini"

    def __init__(
        self,
        caller: GeminiCaller,
        fallback: MockScreenshotExtractor,
        thinking: types.ThinkingConfig | None = None,
    ):
        self.caller = caller
        self._fallback = fallback
        self._thinking = thinking
        self._thinking_tokens = max(0, (thinking.thinking_budget or 0) if thinking else 0)
        self._prompt = load_prompt("screenshot_extract")

    async def extract(self, uri: str) -> Extraction:
        try:
            resp = await self.caller.generate(
                contents=[image_part(uri), self._prompt],
                config=types.GenerateContentConfig(
                    temperature=0.0,
                    response_mime_type="application/json",
                    response_schema=ScreenshotReading,
                    # Thinking tokens count against the cap, so leave room for them.
                    max_output_tokens=512 + self._thinking_tokens,
                    thinking_config=self._thinking,
                ),
            )
            reading = (
                resp.parsed
                if isinstance(resp.parsed, ScreenshotReading)
                else ScreenshotReading.model_validate_json(resp.text or "")
            )
        except Exception as exc:  # noqa: BLE001 — the merchant check must not fail on the LLM
            log.warning("Gemini screenshot extraction failed, using fallback: %s", str(exc)[:300])
            return await self._fallback.extract(uri)
        return Extraction(
            amount=reading.amount,
            txn_id=(reading.txn_id or "").strip() or None,
            vpa=(reading.vpa or "").strip().lower() or None,
            timestamp=_parse_time(reading.timestamp),
            tamper_hints=[TamperHint(h) for h in reading.tamper_hints if h in _VISUAL_HINTS],
            source="gemini",
        )
