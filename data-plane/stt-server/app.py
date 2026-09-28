"""
AIP Speech-to-Text Microservice (Faster-Whisper).
"""

from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
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
    from .config import stt_settings
    from .stt_engine import stt_engine
    from .stt_schemas import TranscriptionResponse
except (ImportError, ValueError):
    from config import stt_settings
    from stt_engine import stt_engine
    from stt_schemas import TranscriptionResponse


@asynccontextmanager
async def lifespan(app: FastAPI):
    stt_engine.initialize()
    yield


stt_app = FastAPI(
    title=f"AIP Speech-to-Text Microservice ({stt_settings.service_name})",
    version=stt_settings.version,
    description="Enterprise Speech-to-Text Pipeline Server powered by Faster-Whisper",
    lifespan=lifespan,
)

stt_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app = stt_app
app.add_middleware(RuntimeAuthMiddleware)
app.add_exception_handler(StarletteHTTPException, aip_http_exception_handler)
app.add_exception_handler(RequestValidationError, aip_validation_exception_handler)
app.add_exception_handler(Exception, aip_unhandled_exception_handler)


@stt_app.post("/v1/audio/transcriptions", response_model=TranscriptionResponse)
async def transcribe_audio(
    file: UploadFile = File(...),
    model: str = Form("stt-vn-standard"),
    language: Optional[str] = Form("vi"),
    beam_size: Optional[int] = Form(None),
    vad_filter: Optional[bool] = Form(None),
    authorization: Optional[str] = Header(None),
):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401, detail="Unauthorized: Bearer API key required"
        )

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Empty audio file provided")

    # Archive audio input to MinIO (SRS Section 2.1 & 3.3)
    try:
        from datetime import datetime
        import uuid
        from common.storage import minio_storage
        date_str = datetime.now().strftime("%Y%m%d")
        safe_name = file.filename or "audio.wav"
        object_name = f"audio/inputs/{date_str}/{uuid.uuid4().hex[:8]}_{safe_name}"
        minio_storage.upload_bytes(
            bucket="aip-data",
            object_name=object_name,
            data=file_bytes,
            content_type=file.content_type or "audio/wav",
        )
    except Exception:
        pass

    try:
        result = await stt_engine.transcribe(
            audio_bytes=file_bytes,
            filename=file.filename or "audio.wav",
            language=language,
            beam_size=beam_size,
            vad_filter=vad_filter,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return result


@stt_app.get("/health", tags=["Health"])
async def health_check():
    return stt_engine.get_status()


@stt_app.get("/v1/capabilities", tags=["Metadata"])
async def capabilities():
    return {
        "service": "stt-server",
        "inference_method": "POST",
        "inference_path": "/v1/audio/transcriptions",
        "accepted_content_type": "multipart/form-data",
        "model": stt_settings.whisper_model_name,
    }
