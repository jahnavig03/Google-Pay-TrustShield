"""POST /api/v1/translate and the Cloud Translation adapter (no network, no credentials)."""

from __future__ import annotations

import json

import httpx
import pytest

from conftest import customer
from trustshield_gateway.adapters.google_translator import GoogleTranslator
from trustshield_gateway.ports import TranslationUnavailable

URL = "/api/v1/translate"


async def test_mock_mode_returns_the_text_unchanged(client):
    resp = await client.post(
        URL, headers=customer(), json={"target_language": "hi", "texts": ["Proceed to pay"]}
    )
    assert resp.status_code == 200
    assert resp.json() == {
        "target_language": "hi",
        "translations": ["Proceed to pay"],
        "provider": "mock",
    }


async def test_needs_a_demo_role(client):
    resp = await client.post(URL, json={"target_language": "hi", "texts": ["Hi"]})
    assert resp.status_code == 401


@pytest.mark.parametrize(
    "body",
    [
        {"target_language": "fr", "texts": ["Hi"]},  # not an offered language
        {"target_language": "hi", "texts": []},
        {"target_language": "hi", "texts": ["x"] * 101},
    ],
)
async def test_rejects_unsupported_or_oversized_requests(client, body):
    resp = await client.post(URL, headers=customer(), json=body)
    assert resp.status_code == 422


class FakeCredentials:
    valid = True
    token = "test-token"


def fake_translation_api(seen: list[dict]):
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen.append({"url": str(request.url), "auth": request.headers["Authorization"], **body})
        return httpx.Response(
            200,
            json={
                "translations": [
                    {"translatedText": f"[{body['targetLanguageCode']}] {t}"}
                    for t in body["contents"]
                ]
            },
        )

    return handler


async def test_google_adapter_calls_translate_text_and_caches_each_text_once():
    seen: list[dict] = []
    translator = GoogleTranslator(
        "demo-project",
        client=httpx.AsyncClient(transport=httpx.MockTransport(fake_translation_api(seen))),
        credentials=FakeCredentials(),
    )
    first = await translator.translate(["Pay {0}", "Messages", "Pay {0}"], "hi")
    assert first == ["[hi] Pay {0}", "[hi] Messages", "[hi] Pay {0}"]
    again = await translator.translate(["Messages", "People"], "hi")
    assert again == ["[hi] Messages", "[hi] People"]

    assert [call["contents"] for call in seen] == [["Pay {0}", "Messages"], ["People"]]
    assert seen[0]["url"].endswith("/projects/demo-project/locations/global:translateText")
    assert seen[0]["auth"] == "Bearer test-token"
    assert seen[0]["sourceLanguageCode"] == "en" and seen[0]["mimeType"] == "text/plain"
    assert await translator.translate(["Messages"], "en") == ["Messages"]  # no call for English
    assert len(seen) == 2


async def test_google_adapter_failure_is_translation_unavailable():
    translator = GoogleTranslator(
        "demo-project",
        client=httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(403))),
        credentials=FakeCredentials(),
    )
    with pytest.raises(TranslationUnavailable):
        await translator.translate(["Messages"], "ta")


async def test_route_turns_a_backend_failure_into_502(memory_app, client):
    class Broken:
        provider = "broken"

        async def translate(self, texts, target_language):
            raise TranslationUnavailable("quota")

        async def close(self):
            return None

    from dataclasses import replace

    memory_app.state.services = replace(memory_app.state.services, translator=Broken())
    resp = await client.post(
        URL, headers=customer(), json={"target_language": "hi", "texts": ["Hi"]}
    )
    assert resp.status_code == 502
