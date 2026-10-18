"""POST /api/v1/translate: the customer app's language setting."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from trustshield_contracts import TranslateRequest, TranslateResponse

from ..deps import TranslatorDep
from ..ports import TranslationUnavailable
from ..security import ANALYST, CUSTOMER, MERCHANT, require_role

router = APIRouter(prefix="/api/v1", tags=["language"])


@router.post(
    "/translate",
    response_model=TranslateResponse,
    operation_id="translateTexts",
    summary="Translate app text into the customer's language",
    dependencies=[Depends(require_role(CUSTOMER, MERCHANT, ANALYST))],
)
async def translate_texts(req: TranslateRequest, translator: TranslatorDep) -> TranslateResponse:
    """Text only: no decision is made here, so nothing is written to the audit log."""
    try:
        translations = await translator.translate(req.texts, req.target_language)
    except TranslationUnavailable as err:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, detail="Translation is unavailable right now."
        ) from err
    return TranslateResponse(
        target_language=req.target_language,
        translations=translations,
        provider=translator.provider,
    )
