import logging
import os
from contextlib import asynccontextmanager
from typing import Optional

logger = logging.getLogger("aip-stt.app")

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

import importlib.util

_grpc_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "grpc_server.py")
_grpc_spec = importlib.util.spec_from_file_location("stt_engine_grpc_server", _grpc_path)
_grpc_mod = importlib.util.module_from_spec(_grpc_spec)
_grpc_spec.loader.exec_module(_grpc_mod)
create_stt_grpc_server = _grpc_mod.create_stt_grpc_server


@asynccontextmanager
async def lifespan(app: FastAPI):
    stt_engine.initialize()

    grpc_server = None
    grpc_port = int(os.getenv("GRPC_PORT", "50052"))

    try:
        grpc_server = await create_stt_grpc_server(host="0.0.0.0", port=grpc_port)
        await grpc_server.start()
        logger.info("[Dual Arterial] STT gRPC server running on port %d", grpc_port)
    except Exception as exc:
        logger.error("[Dual Arterial] Failed to start STT gRPC server on port %d: %s", grpc_port, exc)

    yield

    if grpc_server:
        logger.info("[Dual Arterial] Shutting down STT gRPC server...")
        await grpc_server.stop(grace=5.0)


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
