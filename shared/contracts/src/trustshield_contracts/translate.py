"""Translation for the customer app's language setting (Cloud Translation in gcp mode)."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator, model_validator

#: Languages the customer can pick, as BCP-47 codes Cloud Translation accepts. English is the
#: source language of every string the app shows.
SUPPORTED_LANGUAGES: dict[str, str] = {
    "en": "English",
    "hi": "हिन्दी",
    "bn": "বাংলা",
    "te": "తెలుగు",
    "mr": "मराठी",
    "ta": "தமிழ்",
    "gu": "ગુજરાતી",
    "kn": "ಕನ್ನಡ",
    "ml": "മലയാളം",
    "pa": "ਪੰਜਾਬੀ",
    "or": "ଓଡ଼ିଆ",
}
MAX_TEXTS = 100
MAX_TEXT_CHARS = 2000
MAX_TOTAL_CHARS = 20_000


class TranslateRequest(BaseModel):
    target_language: str = Field(examples=["hi"])
    texts: list[str] = Field(min_length=1, max_length=MAX_TEXTS, examples=[["Proceed to pay"]])

    @field_validator("target_language")
    @classmethod
    def _supported(cls, value: str) -> str:
        if value not in SUPPORTED_LANGUAGES:
            raise ValueError(f"unsupported language {value!r}")
        return value

    @field_validator("texts")
    @classmethod
    def _short_enough(cls, texts: list[str]) -> list[str]:
        if any(len(t) > MAX_TEXT_CHARS for t in texts):
            raise ValueError(f"each text must be at most {MAX_TEXT_CHARS} characters")
        return texts

    @model_validator(mode="after")
    def _total(self) -> TranslateRequest:
        if sum(len(t) for t in self.texts) > MAX_TOTAL_CHARS:
            raise ValueError(f"texts must total at most {MAX_TOTAL_CHARS} characters")
        return self


class TranslateResponse(BaseModel):
    """``translations[i]`` is ``texts[i]`` in ``target_language`` (same order, same length)."""

    target_language: str
    translations: list[str]
    provider: str = Field(examples=["google-cloud-translation"])
