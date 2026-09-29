"""
AIP Content Moderation Server (Llama-Guard-3 & Hybrid Rule Engine).
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
    from .config import moderation_settings
    from .moderation_engine import moderation_engine
    from .moderation_schemas import ModerationRequest, ModerationResponse
except (ImportError, ValueError):
    from config import moderation_settings
    from moderation_engine import moderation_engine
    from moderation_schemas import ModerationRequest, ModerationResponse


@asynccontextmanager
async def lifespan(app: FastAPI):
    moderation_engine.initialize()
    yield


moderation_app = FastAPI(
    title=f"AIP Moderation Server ({moderation_settings.service_name})",
    version=moderation_settings.version,
    description="Enterprise Content Moderation Microservice powered by Llama Guard 4 & Hybrid Rules",
    lifespan=lifespan,
)

moderation_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app = moderation_app
app.add_middleware(RuntimeAuthMiddleware)
app.add_exception_handler(StarletteHTTPException, aip_http_exception_handler)
app.add_exception_handler(RequestValidationError, aip_validation_exception_handler)
app.add_exception_handler(Exception, aip_unhandled_exception_handler)


@moderation_app.post("/v1/moderations", response_model=ModerationResponse)
async def moderate_content(
    request: ModerationRequest,
    authorization: str | None = Header(None),
):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401, detail="Unauthorized: Bearer API key required"
        )

    inputs = [request.input] if isinstance(request.input, str) else request.input
    try:
        return await moderation_engine.moderate(inputs, model=request.model)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@moderation_app.get("/health", tags=["Health"])
async def health_check():
    return moderation_engine.get_status()


@moderation_app.get("/v1/capabilities", tags=["Metadata"])
async def capabilities():
    return {
        "service": "moderation-server",
        "inference_method": "POST",
        "inference_path": "/v1/moderations",
        "accepted_content_type": "application/json",
        "model": moderation_settings.model_name,
    }
