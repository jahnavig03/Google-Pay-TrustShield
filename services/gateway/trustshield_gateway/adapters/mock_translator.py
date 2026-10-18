"""Mock translator: returns the English text unchanged, so the app works with no credentials."""

from __future__ import annotations


class MockTranslator:
    provider = "mock"

    async def translate(self, texts: list[str], target_language: str) -> list[str]:
        del target_language
        return list(texts)

    async def close(self) -> None:
        return None
