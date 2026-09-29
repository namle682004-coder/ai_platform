"""
AIP CTranslate2 Machine Translation Microservice.
Compliant with Clean Architecture Data-Plane & SRS Section 2.3 & 6.1.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI, Header, HTTPException
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.middleware.cors import CORSMiddleware
from common.security.runtime_auth import RuntimeAuthMiddleware
from common.errors import (
    aip_http_exception_handler,
    aip_unhandled_exception_handler,
    aip_validation_exception_handler,
)

try:
    from .config import translation_settings
    from .translation_engine import translation_engine
    from .translation_schemas import (
        TranslationRequest,
        TranslationResponse,
    )
except (ImportError, ValueError):
    from config import translation_settings
    from translation_engine import translation_engine
    from translation_schemas import (
        TranslationRequest,
        TranslationResponse,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    translation_engine.initialize()
    yield


translation_app = FastAPI(
    title=f"AIP Neural Translation Microservice ({translation_settings.service_name})",
    version=translation_settings.version,
    description="CTranslate2 High-Performance Machine Translation Microservice",
    lifespan=lifespan,
)

translation_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app = translation_app
app.add_middleware(RuntimeAuthMiddleware)
app.add_exception_handler(StarletteHTTPException, aip_http_exception_handler)
app.add_exception_handler(RequestValidationError, aip_validation_exception_handler)
app.add_exception_handler(Exception, aip_unhandled_exception_handler)


@translation_app.post("/v1/predictions", response_model=TranslationResponse)
async def translate_single(
    request: TranslationRequest,
    authorization: str | None = Header(None),
):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401, detail="Unauthorized: Bearer API key required"
        )

    try:
        res = await translation_engine.translate_text(
            text=request.text,
            source_lang=request.source_lang,
            target_lang=request.target_lang,
            beam_size=request.beam_size,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return TranslationResponse(
        model=translation_settings.model_name,
        translated_text=res["translated_text"],
        source_lang=request.source_lang,
        target_lang=request.target_lang,
        usage={
            "prompt_tokens": res["prompt_tokens"],
            "completion_tokens": res["completion_tokens"],
            "total_tokens": res["total_tokens"],
            "character_count": res["character_count"],
            "word_count": res["word_count"],
        },
        metadata={
            "backend": res["backend"],
            "device": res["device"],
            "compute_type": res["compute_type"],
            "beam_size": res["beam_size"],
            "repetition_penalty": 1.2,
            "no_repeat_ngram_size": 3,
            "latency_ms": res["execution_time_ms"],
        },
    )


@translation_app.get("/health", tags=["Health"])
async def health_check():
    return translation_engine.get_status()


@translation_app.get("/v1/capabilities", tags=["Metadata"])
async def capabilities():
    return {
        "service": "translation-server",
        "inference_method": "POST",
        "inference_path": "/v1/predictions",
        "accepted_content_type": "application/json",
        "model": translation_settings.model_name,
    }
