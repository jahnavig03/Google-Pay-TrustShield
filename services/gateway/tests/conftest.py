"""Shared fixtures. Tests run in mock mode with the in-process store unless a Firestore
emulator is configured, so `pytest` needs neither Java nor GCP credentials."""

from __future__ import annotations

import os
import socket

import pytest

os.environ.setdefault("TRUSTSHIELD_MODE", "mock")


def _emulator_reachable() -> bool:
    host = os.environ.get("FIRESTORE_EMULATOR_HOST", "").strip()
    if not host:
        return False
    name, _, port = host.partition(":")
    try:
        with socket.create_connection((name or "localhost", int(port or 8080)), timeout=0.5):
            return True
    except OSError:
        return False


#: True when `firebase emulators:start --only firestore` is running on FIRESTORE_EMULATOR_HOST.
FIRESTORE_EMULATOR_RUNNING = _emulator_reachable()

requires_firestore_emulator = pytest.mark.skipif(
    not FIRESTORE_EMULATOR_RUNNING,
    reason="Firestore emulator not running (set FIRESTORE_EMULATOR_HOST and start it).",
)


@pytest.fixture
def memory_app(monkeypatch):
    """App backed by the in-process store and the no-op publisher."""
    monkeypatch.setenv("TRUSTSHIELD_MODE", "mock")
    monkeypatch.setenv("TRUSTSHIELD_DOC_STORE", "memory")
    monkeypatch.setenv("TRUSTSHIELD_PUBLISHER", "noop")
    from trustshield_gateway.app import create_app

    return create_app()


@pytest.fixture
def emulator_app(monkeypatch):
    """App backed by the Firestore emulator. Only used by emulator-marked tests."""
    monkeypatch.setenv("TRUSTSHIELD_MODE", "mock")
    monkeypatch.setenv("TRUSTSHIELD_DOC_STORE", "firestore")
    monkeypatch.setenv("TRUSTSHIELD_PUBLISHER", "noop")
    from trustshield_gateway.app import create_app

    return create_app()


@pytest.fixture
async def client(memory_app):
    import httpx

    transport = httpx.ASGITransport(app=memory_app)
    async with (
        httpx.AsyncClient(transport=transport, base_url="http://gateway") as http,
        memory_app.router.lifespan_context(memory_app),
    ):
        yield http


def customer(**extra) -> dict[str, str]:
    return {"X-Demo-Role": "customer", **extra}


def analyst(**extra) -> dict[str, str]:
    return {"X-Demo-Role": "analyst", **extra}


def merchant(**extra) -> dict[str, str]:
    return {"X-Demo-Role": "merchant", **extra}
