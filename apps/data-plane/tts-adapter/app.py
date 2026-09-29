"""
AIP Text-to-Speech Adapter (viXTTS & OpenVoice).
Generates Neural Speech and Automatically Archives Audio Artifacts to MinIO.
"""

from contextlib import asynccontextmanager
from datetime import datetime, timezone
import uuid
import logging

from fastapi import FastAPI, Header, HTTPException, Response
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
    from .config import tts_settings
    from .tts_engine import tts_engine
    from .tts_schemas import TTSRequest, VoiceListResponse
except (ImportError, ValueError):
    from config import tts_settings
    from tts_engine import tts_engine
    from tts_schemas import TTSRequest, VoiceListResponse

from common.storage import minio_storage

logger = logging.getLogger("aip-tts.app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    tts_engine.initialize()
    yield


tts_app = FastAPI(
    title=f"AIP Text-to-Speech Adapter ({tts_settings.service_name})",
    version=tts_settings.version,
    description="Enterprise Text-to-Speech Audio Synthesis & Voice Cloning Microservice",
    lifespan=lifespan,
)

tts_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app = tts_app
app.add_middleware(RuntimeAuthMiddleware)
app.add_exception_handler(StarletteHTTPException, aip_http_exception_handler)
app.add_exception_handler(RequestValidationError, aip_validation_exception_handler)
app.add_exception_handler(Exception, aip_unhandled_exception_handler)


@tts_app.get("/v1/audio/speech", summary="Quick Browser Audio Synthesis (GET)")
async def generate_speech_browser(
    input: str = "Xin chào, đây là hệ thống chuyển đổi văn bản thành giọng nói.",
    voice: str = "northern_female",
    response_format: str = "mp3",
):
    media_type = "audio/mpeg" if response_format.lower() == "mp3" else "audio/wav"
    ext = response_format.lower()

    chunks = []
    try:
        async for chunk in tts_engine.generate_speech_stream(
            text=input,
            voice=voice,
            response_format=response_format,
        ):
            chunks.append(chunk)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    audio_data = b"".join(chunks)
    if not audio_data:
        raise HTTPException(status_code=503, detail="TTS provider produced no audio")

    # Archive to MinIO (SRS Section 2.1 & 3.3)
    obj_name = f"audio/speech/{datetime.now(timezone.utc).strftime('%Y%m%d')}/tts_{uuid.uuid4().hex[:10]}.{ext}"
    try:
        minio_storage.upload_bytes(
            bucket="aip-job-artifacts",
            object_name=obj_name,
            data=audio_data,
            content_type=media_type,
        )
        minio_storage.upload_bytes(
            bucket="aip-data",
            object_name=obj_name,
            data=audio_data,
            content_type=media_type,
        )
    except Exception as exc:
        logger.warning(f"Failed to archive TTS audio to MinIO: {exc}")

    return Response(
        content=audio_data,
        media_type=media_type,
        headers={
            "X-AIP-Storage-Bucket": "aip-job-artifacts",
            "X-AIP-Storage-Key": obj_name,
        },
    )


@tts_app.post("/v1/audio/speech")
async def generate_speech(
    request: TTSRequest,
    authorization: str | None = Header(None),
):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401, detail="Unauthorized: Bearer API key required"
        )

    if not request.input.strip():
        raise HTTPException(status_code=400, detail="Input text cannot be empty")

    media_type = (
        "audio/mpeg" if request.response_format.lower() == "mp3" else "audio/wav"
    )
    ext = request.response_format.lower()

    chunks = []
    try:
        async for chunk in tts_engine.generate_speech_stream(
            text=request.input,
            voice=request.voice,
            response_format=request.response_format,
        ):
            chunks.append(chunk)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    audio_data = b"".join(chunks)
    if not audio_data:
        raise HTTPException(status_code=503, detail="TTS provider produced no audio")

    # Archive to MinIO (SRS Section 2.1 & 3.3)
    obj_name = f"audio/speech/{datetime.now(timezone.utc).strftime('%Y%m%d')}/tts_{uuid.uuid4().hex[:10]}.{ext}"
    try:
        minio_storage.upload_bytes(
            bucket="aip-job-artifacts",
            object_name=obj_name,
            data=audio_data,
            content_type=media_type,
        )
        minio_storage.upload_bytes(
            bucket="aip-data",
            object_name=obj_name,
            data=audio_data,
            content_type=media_type,
        )
    except Exception as exc:
        logger.warning(f"Failed to archive TTS audio to MinIO: {exc}")

    return Response(
        content=audio_data,
        media_type=media_type,
        headers={
            "X-AIP-Storage-Bucket": "aip-job-artifacts",
            "X-AIP-Storage-Key": obj_name,
        },
    )


@tts_app.get("/v1/audio/voices", response_model=VoiceListResponse)
async def list_available_voices():
    return VoiceListResponse(voices=tts_engine.list_voices())


@tts_app.get("/health", tags=["Health"])
async def health_check():
    return tts_engine.get_status()


@tts_app.get("/v1/capabilities", tags=["Metadata"])
async def capabilities():
    return {
        "service": "tts-adapter",
        "inference_method": "POST",
        "inference_path": "/v1/audio/speech",
        "accepted_content_type": "application/json",
        "voices_path": "/v1/audio/voices",
    }
