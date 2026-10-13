"""Uvicorn entry point: `uvicorn main:app --reload` from services/gateway."""

from __future__ import annotations

from trustshield_gateway.app import create_app

app = create_app()
