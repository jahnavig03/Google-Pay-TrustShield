"""Translator port: Cloud Translation in gcp mode, pass-through in mock mode."""

from __future__ import annotations

from typing import Protocol


class TranslationUnavailable(RuntimeError):
    """The translation backend failed; the app keeps showing English."""


class Translator(Protocol):
    provider: str

    async def translate(self, texts: list[str], target_language: str) -> list[str]:
        """``texts`` (English) in ``target_language``, same order and length."""
        ...

    async def close(self) -> None: ...
