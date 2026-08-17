
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
tokenizer_vi_en = None
model_vi_en = None
tokenizer_en_vi = None
model_en_vi = None
ml_initialized = False
init_error = None
device_name = "cpu"


def init_ml():
    global tokenizer_vi_en, model_vi_en, tokenizer_en_vi, model_en_vi, ml_initialized, init_error, device_name
    if ml_initialized:
        return
    try:
        import torch
        from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
        
        # Detect CUDA GPU
        device_id = "cuda" if torch.cuda.is_available() else "cpu"
        device = torch.device(device_id)
        device_name = torch.cuda.get_device_name(0) if torch.cuda.is_available() else "cpu"
        
        # Load lightweight Helsinki-NLP models (approx. 150MB each, fits easily on 3050 GPU)
        model_en_vi_name = "Helsinki-NLP/opus-mt-en-vi"
        tokenizer_en_vi = AutoTokenizer.from_pretrained(model_en_vi_name)
        model_en_vi = AutoModelForSeq2SeqLM.from_pretrained(model_en_vi_name).to(device)
        
        model_vi_en_name = "Helsinki-NLP/opus-mt-vi-en"
        tokenizer_vi_en = AutoTokenizer.from_pretrained(model_vi_en_name)
        model_vi_en = AutoModelForSeq2SeqLM.from_pretrained(model_vi_en_name).to(device)
        
        ml_initialized = True
        init_error = None
    except Exception as e:
        init_error = str(e)
        ml_initialized = False


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
            import torch
            device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
            
            src = "vi" if "vi" in request.source_lang.lower() else "en"
            tgt = "en" if "en" in request.target_lang.lower() else "vi"

            if src == "vi" and tgt == "en" and tokenizer_vi_en and model_vi_en:
                inputs = tokenizer_vi_en(request.text, return_tensors="pt", padding=True).to(device)
                with torch.no_grad():
                    outputs = model_vi_en.generate(**inputs)
                translated_text = tokenizer_vi_en.decode(outputs[0], skip_special_tokens=True)
            elif src == "en" and tgt == "vi" and tokenizer_en_vi and model_en_vi:
                inputs = tokenizer_en_vi(request.text, return_tensors="pt", padding=True).to(device)
                with torch.no_grad():
                    outputs = model_en_vi.generate(**inputs)
                translated_text = tokenizer_en_vi.decode(outputs[0], skip_special_tokens=True)
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
    mock_translated = f"[Simulated Translation]: {request.text} (Please verify torch, transformers, sentencepiece and sacremoses inside .venv. Error: {init_error})"
    return TranslationResponse(
        translated_text=mock_translated,
        source_lang=request.source_lang,
        target_lang=request.target_lang,
        execution_time_ms=elapsed,
    )


@translation_app.get("/health", tags=["Health"])
async def health_check():
    init_ml()
    backend_status = f"Helsinki-NLP (Live GPU Engine: {device_name})" if ml_initialized else "Mock/Fallback Engine"
    cuda_status = ml_initialized and ("cuda" in str(device_name).lower() or device_name != "cpu")
    return {
        "status": "healthy",
        "service": "translation-server",
        "backend": backend_status,
        "cuda_available": bool(cuda_status),
        "init_error": init_error
    }
