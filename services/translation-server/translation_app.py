from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel, Field
from typing import Optional

translation_app = FastAPI(
    title="AIP Translation Server (CTranslate2)",
    version="1.0.0",
    description="CTranslate2 NLLB-200 Machine Translation Microservice",
)


class TranslationRequest(BaseModel):
    text: str = Field(..., json_schema_extra={"example": "Xin chào thế giới"})
    source_lang: str = Field("vie_Latn", json_schema_extra={"example": "vie_Latn"})
    target_lang: str = Field("eng_Latn", json_schema_extra={"example": "eng_Latn"})


class TranslationResponse(BaseModel):
    translated_text: str
    source_lang: str
    target_lang: str
    execution_time_ms: float = 12.5


@translation_app.post("/v1/predictions", response_model=TranslationResponse)
async def translate_text(
    request: TranslationRequest,
    authorization: Optional[str] = Header(None),
):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized: Bearer API key required")

    mock_translated = f"[EN Translation]: {request.text} (Translated by CTranslate2 Engine)"
    return TranslationResponse(
        translated_text=mock_translated,
        source_lang=request.source_lang,
        target_lang=request.target_lang,
        execution_time_ms=14.2,
    )


@translation_app.get("/health", tags=["Health"])
async def health_check():
    return {"status": "healthy", "service": "translation-server", "backend": "CTranslate2 NLLB-200"}
