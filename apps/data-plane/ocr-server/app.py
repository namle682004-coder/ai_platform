"""
AIP OCR & Document Server (Triton / PaddleOCR-VL).
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, File, Header, HTTPException, UploadFile
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.middleware.cors import CORSMiddleware
from common.security.runtime_auth import RuntimeAuthMiddleware
from common.errors import (
    aip_http_exception_handler,
    aip_unhandled_exception_handler,
    aip_validation_exception_handler,
)

import os
import importlib.util
import logging

try:
    from .config import ocr_settings
    from .ocr_engine import ocr_engine
    from .ocr_schemas import OCRResponse
except (ImportError, ValueError):
    from config import ocr_settings
    from ocr_engine import ocr_engine
    from ocr_schemas import OCRResponse

_grpc_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "grpc_server.py")
_grpc_spec = importlib.util.spec_from_file_location("ocr_engine_grpc_server", _grpc_path)
_grpc_mod = importlib.util.module_from_spec(_grpc_spec)
_grpc_spec.loader.exec_module(_grpc_mod)
create_ocr_grpc_server = _grpc_mod.create_ocr_grpc_server
logger = logging.getLogger("aip-ocr.app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    ocr_engine.initialize()

    grpc_server = None
    grpc_port = int(os.getenv("GRPC_PORT", "50054"))

    try:
        grpc_server = await create_ocr_grpc_server(host="0.0.0.0", port=grpc_port)
        await grpc_server.start()
        logger.info("[Dual Arterial] OCR gRPC server running on port %d", grpc_port)
    except Exception as exc:
        logger.error("[Dual Arterial] Failed to start OCR gRPC server on port %d: %s", grpc_port, exc)

    yield

    if grpc_server:
        logger.info("[Dual Arterial] Shutting down OCR gRPC server...")
        await grpc_server.stop(grace=5.0)


ocr_app = FastAPI(
    title=f"AIP OCR & Document Server ({ocr_settings.service_name})",
    version=ocr_settings.version,
    description="Enterprise Vision-Language Document Processing Microservice powered by Triton & PaddleOCR-VL",
    lifespan=lifespan,
)

ocr_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app = ocr_app
app.add_middleware(RuntimeAuthMiddleware)
app.add_exception_handler(StarletteHTTPException, aip_http_exception_handler)
app.add_exception_handler(RequestValidationError, aip_validation_exception_handler)
app.add_exception_handler(Exception, aip_unhandled_exception_handler)


@ocr_app.post("/v1/ocr/process", response_model=OCRResponse)
async def process_document_ocr(
    file: UploadFile = File(...),
    authorization: str | None = Header(None),
):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401, detail="Unauthorized: Bearer API key required"
        )

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(
            status_code=400, detail="Empty document/image file uploaded"
        )

    # Archive document/image to MinIO (SRS Section 2.1 & 3.3)
    try:
        from datetime import datetime
        import uuid
        from common.storage import minio_storage
        date_str = datetime.now().strftime("%Y%m%d")
        safe_name = file.filename or "document.jpg"
        object_name = f"documents/inputs/{date_str}/{uuid.uuid4().hex[:8]}_{safe_name}"
        minio_storage.upload_bytes(
            bucket="aip-data",
            object_name=object_name,
            data=file_bytes,
            content_type=file.content_type or "image/jpeg",
        )
    except Exception:
        pass

    try:
        return await ocr_engine.process_document(
            file_bytes, file.filename or "document.pdf"
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@ocr_app.get("/health", tags=["Health"])
async def health_check():
    return ocr_engine.get_status()


@ocr_app.get("/v1/capabilities", tags=["Metadata"])
async def capabilities():
    return {
        "service": "ocr-server",
        "inference_method": "POST",
        "inference_path": "/v1/ocr/process",
        "accepted_content_type": "multipart/form-data",
        "model": ocr_settings.det_model_name,
    }
