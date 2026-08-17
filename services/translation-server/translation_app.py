
import time
import os
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

translation_app = FastAPI(
    title="AIP Translation Server (Helsinki-NLP)",
    version="1.0.0",
    description="Helsinki-NLP Machine Translation Microservice with PyTorch & CUDA support",
)


class TranslationRequest(BaseModel):
    text: str = Field(..., json_schema_extra={"example": "Xin chào thế giới"})
    source_lang: str = Field("vie_Latn", json_schema_extra={"example": "vie_Latn"})
    target_lang: str = Field("eng_Latn", json_schema_extra={"example": "eng_Latn"})


class TranslationResponse(BaseModel):
    translated_text: str
    source_lang: str
    target_lang: str
    execution_time_ms: float


# Lazy load ML models on first request to prevent startup crash if packages are missing
translator_vi_en = None
translator_en_vi = None
ml_initialized = False
init_error = None


def init_ml():
    global translator_vi_en, translator_en_vi, ml_initialized, init_error
    if ml_initialized:
        return
    try:
        import torch
        from transformers import pipeline
        
        # Detect CUDA GPU
        device = 0 if torch.cuda.is_available() else -1
        
        # Load lightweight Helsinki-NLP models (approx. 150MB each, fits easily on 3050 GPU)
        translator_en_vi = pipeline("translation", model="Helsinki-NLP/opus-mt-en-vi", device=device)
        translator_vi_en = pipeline("translation", model="Helsinki-NLP/opus-mt-vi-en", device=device)
        
        ml_initialized = True
        init_error = None
    except Exception as e:
        init_error = str(e)


@translation_app.post("/v1/predictions", response_model=TranslationResponse)
async def translate_text(
    request: TranslationRequest,
    authorization: str | None = Header(None),
):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized: Bearer API key required")

    start_time = time.time()
    init_ml()

    # 1. Real-time Inference using GPU/CPU Model
    if ml_initialized:
        try:
            src = "vi" if "vi" in request.source_lang.lower() else "en"
            tgt = "en" if "en" in request.target_lang.lower() else "vi"

            if src == "vi" and tgt == "en" and translator_vi_en:
                res = translator_vi_en(request.text)
                translated_text = res[0]["translation_text"]
            elif src == "en" and tgt == "vi" and translator_en_vi:
                res = translator_en_vi(request.text)
                translated_text = res[0]["translation_text"]
            else:
                translated_text = f"[Model Fallback] Translation from {request.source_lang} to {request.target_lang} is not loaded."

            elapsed = (time.time() - start_time) * 1000
            return TranslationResponse(
                translated_text=translated_text,
                source_lang=request.source_lang,
                target_lang=request.target_lang,
                execution_time_ms=elapsed,
            )
        except Exception as e:
            # Graceful model inference error fallback
            elapsed = (time.time() - start_time) * 1000
            return TranslationResponse(
                translated_text=f"[Real model runtime error: {str(e)}]. Input: {request.text}",
                source_lang=request.source_lang,
                target_lang=request.target_lang,
                execution_time_ms=elapsed,
            )

    # 2. Local Fallback if torch/transformers packages are not installed in the .venv
    elapsed = (time.time() - start_time) * 1000
    mock_translated = f"[Simulated Translation]: {request.text} (Please install torch, transformers, sacremoses inside .venv to run real CUDA inference. Error: {init_error})"
    return TranslationResponse(
        translated_text=mock_translated,
        source_lang=request.source_lang,
        target_lang=request.target_lang,
        execution_time_ms=elapsed,
    )


@translation_app.get("/health", tags=["Health"])
async def health_check():
    init_ml()
    backend_status = "Helsinki-NLP (Live GPU/CPU Engine)" if ml_initialized else "Mock/Fallback Engine"
    return {
        "status": "healthy",
        "service": "translation-server",
        "backend": backend_status,
        "cuda_available": ml_initialized and translator_vi_en is not None,
        "init_error": init_error
    }
