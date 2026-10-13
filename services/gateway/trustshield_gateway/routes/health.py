"""Liveness probe. No role header, no /api/v1 prefix: Cloud Run and the team both use it."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


@router.get("/health", tags=["ops"], summary="Liveness probe")
async def health() -> dict[str, str]:
    return {"status": "ok"}
