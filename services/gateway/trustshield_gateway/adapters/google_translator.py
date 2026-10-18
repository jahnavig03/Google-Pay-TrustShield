"""Cloud Translation (v3 REST, ``translateText``) with an in-process cache.

Each distinct (language, text) pair is translated once per instance, so the app's fixed labels
cost a handful of characters per language, well inside the free 500k characters a month.
Names, amounts and UPI IDs are passed as ``{0}``-style placeholders, which Cloud Translation keeps.
"""

from __future__ import annotations

import asyncio
from collections import OrderedDict

import google.auth
import httpx
from google.auth.transport.requests import Request as AuthRequest

from ..ports import TranslationUnavailable

ENDPOINT = "https://translation.googleapis.com/v3/projects/{project}/locations/global:translateText"
SCOPES = ["https://www.googleapis.com/auth/cloud-translation"]
CACHE_SIZE = 5000
TIMEOUT_S = 10.0


class GoogleTranslator:
    provider = "google-cloud-translation"

    def __init__(self, project: str, client: httpx.AsyncClient | None = None, credentials=None):
        self._url = ENDPOINT.format(project=project)
        self._project = project
        self._client = client or httpx.AsyncClient(timeout=TIMEOUT_S)
        self._credentials = credentials
        self._cache: OrderedDict[tuple[str, str], str] = OrderedDict()
        self._auth_lock = asyncio.Lock()

    async def _token(self) -> str:
        async with self._auth_lock:
            if self._credentials is None:
                self._credentials, _ = await asyncio.to_thread(google.auth.default, scopes=SCOPES)
            if not self._credentials.valid:
                await asyncio.to_thread(self._credentials.refresh, AuthRequest())
            return self._credentials.token

    async def translate(self, texts: list[str], target_language: str) -> list[str]:
        if target_language == "en":
            return list(texts)
        missing = list(dict.fromkeys(t for t in texts if (target_language, t) not in self._cache))
        if missing:
            for text, translated in zip(missing, await self._call(missing, target_language)):
                self._remember((target_language, text), translated)
        return [self._cache[(target_language, t)] for t in texts]

    async def _call(self, texts: list[str], target_language: str) -> list[str]:
        try:
            resp = await self._client.post(
                self._url,
                headers={
                    "Authorization": f"Bearer {await self._token()}",
                    "x-goog-user-project": self._project,
                },
                json={
                    "contents": texts,
                    "sourceLanguageCode": "en",
                    "targetLanguageCode": target_language,
                    "mimeType": "text/plain",
                },
            )
            resp.raise_for_status()
            translations = [t["translatedText"] for t in resp.json()["translations"]]
        except Exception as err:  # network, auth, quota or a malformed reply
            raise TranslationUnavailable(str(err)) from err
        if len(translations) != len(texts):
            raise TranslationUnavailable("Cloud Translation returned a different number of texts")
        return translations

    def _remember(self, key: tuple[str, str], value: str) -> None:
        self._cache[key] = value
        self._cache.move_to_end(key)
        while len(self._cache) > CACHE_SIZE:
            self._cache.popitem(last=False)

    async def close(self) -> None:
        await self._client.aclose()
