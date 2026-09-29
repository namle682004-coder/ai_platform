import uuid
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from common.errors import aip_unhandled_exception_handler
from starlette.responses import JSONResponse

from common.models.schemas import AIPErrorResponse, AIPError
from src.configs.settings import gateway_settings
from src.auth import AuthMiddleware, AdminCIDRMiddleware
from src.auth.request_id import RequestIDMiddleware
from src.quota import QuotaMiddleware
from src.metrics import PrometheusMetricsMiddleware
from src.publisher import setup_rabbitmq_topology, TaskPublisher

# 1. Standard AI Routers (OpenAI-compatible)
from src.api.chat import router as chat_router
from src.api.completions import router as completions_router
from src.api.embeddings import router as embeddings_router
from src.api.audio import router as audio_router
from src.api.images import router as images_router
from src.api.moderations import router as moderations_router
from src.api.models import router as models_router

# 2. Enterprise Specialized Domain Routers
from src.api.ocr import router as ocr_router
from src.api.vision import router as vision_router
from src.api.nlp import router as nlp_router, v1_router as nlp_v1_router

# 3. Async Tasks & Platform Routers
from src.api.jobs import router as jobs_router
from src.api.predictions import router as predictions_router
from src.api.auth import router as auth_router
from src.api.mcp import router as mcp_router
from src.api.user_portal import router as user_portal_router
from src.api.simulations import router as simulations_router
from src.api.usage import router as usage_router

# Admin Routers
from src.admin.keys import router as admin_keys_router
from src.admin.aliases import router as admin_aliases_router
from src.admin.audit import router as admin_audit_router
from src.admin.endpoints import router as admin_endpoints_router
from src.admin.metrics import router as admin_metrics_router
from src.admin.maintenance import router as admin_maintenance_router
from src.admin.users import router as admin_users_router

# Status Router
from src.status.health import router as status_router
from common.repositories.mongo_repositories import endpoint_repository
from src.items.alias_router import alias_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    import logging
    from common.database.mongodb import mongo_manager

    logger = logging.getLogger("aip-control-plane.lifespan")

    # 1. Connect MongoDB
    try:
        await mongo_manager.connect(
            uri=gateway_settings.mongo_uri, db_name="ai_platform"
        )
        logger.info("MongoDB client connected")
    except Exception as exc:
        logger.warning(f"MongoDB connection failed: {exc}")

    # Prime DB-backed routing and endpoint state before serving requests.
    try:
        await alias_router.refresh()
        await endpoint_repository.list_endpoints()
        logger.info("Alias and endpoint registries loaded")
    except Exception as exc:
        logger.warning(
            f"Registry preload failed; catalog fallbacks remain active: {exc}"
        )

    alias_sync_task = asyncio.create_task(alias_router.listen_for_updates())

    # 2. Idempotent RabbitMQ Topology Setup & Task Publisher
    task_publisher = None
    try:
        await setup_rabbitmq_topology(gateway_settings.rabbitmq_url)
        task_publisher = TaskPublisher(gateway_settings.rabbitmq_url)
        await task_publisher.connect()
        app.state.task_publisher = task_publisher
        logger.info(
            "RabbitMQ topology initialized and Control-Plane TaskPublisher connected"
        )
    except Exception as exc:
        logger.warning(
            f"RabbitMQ initialization degraded (running in fallback mode): {exc}"
        )

    # 3. Start Background Maintenance Scheduler (DCP pattern)
    from src.jobs.scheduler import job_scheduler

    job_scheduler.start()

    yield

    # Shutdown Maintenance Scheduler
    try:
        await job_scheduler.stop()
    except Exception as exc:
        logger.warning(f"Error stopping JobScheduler: {exc}")

    alias_sync_task.cancel()
    try:
        await alias_sync_task
    except asyncio.CancelledError:
        pass

    # Shutdown Publisher
    if task_publisher is not None:
        try:
            await task_publisher.close()
            logger.info("Control-Plane TaskPublisher closed cleanly")
        except Exception as exc:
            logger.warning(f"Error closing TaskPublisher: {exc}")


OPENAPI_TAGS = [
    {
        "name": "Chat Completions",
        "description": "Standard OpenAI-compatible Chat completion & reasoning interface (Qwen2.5 / DeepSeek with SSE Streaming).",
    },
    {"name": "Completions", "description": "Raw text prompt completion interface."},
    {
        "name": "Embeddings",
        "description": "Dense high-dimensional vector embeddings for semantic search & RAG.",
    },
    {
        "name": "Audio (STT & TTS)",
        "description": "Audio transcription (Whisper ASR) & Speech synthesis (viXTTS).",
    },
    {
        "name": "Images",
        "description": "Text-to-image generation via FLUX.1 & Stable Diffusion XL.",
    },
    {
        "name": "Moderations",
        "description": "Content safety, toxicity detection & policy enforcement (Llama-Guard).",
    },
    {
        "name": "Models",
        "description": "SRS Section 6.1 official 21-model catalog & runtime alias resolver.",
    },
    {
        "name": "Document OCR & Intelligent Document Processing",
        "description": "Document analysis, invoice scanning, CCCD, Driver License, and Passport OCR.",
    },
    {
        "name": "Computer Vision & Biometric eKYC",
        "description": "1:1 Face matching and anti-spoofing liveness detection.",
    },
    {
        "name": "Natural Language Processing (Translation & Summarization)",
        "description": "Bilingual machine translation (Helsinki-NLP) and executive document summarization.",
    },
    {
        "name": "Jobs",
        "description": "Asynchronous heavy job status polling and cancellation.",
    },
    {
        "name": "User Portal & Console API",
        "description": "Developer console: Projects, Keys, Balance & Service subscriptions.",
    },
    {
        "name": "Authentication",
        "description": "User login, registration & token exchange.",
    },
]

bearer_scheme = HTTPBearer(auto_error=False)

app = FastAPI(
    title="AIP Platform - Enterprise Control Plane",
    version="1.0.0",
    description="Enterprise Multi-tenant AI Gateway & Inference Middleware Platform",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_tags=OPENAPI_TAGS,
    dependencies=[Depends(bearer_scheme)],
    lifespan=lifespan,
)


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request, exc: StarletteHTTPException):
    request_id = request.headers.get("X-Request-ID") or f"req_{uuid.uuid4().hex[:12]}"
    status_code = exc.status_code
    error_mapping = {
        400: ("invalid_request_error", "bad_request", False),
        401: ("authentication_error", "unauthorized", False),
        403: ("permission_error", "forbidden_alias", False),
        404: ("not_found_error", "not_found", False),
        429: ("rate_limit_error", "rate_limit_exceeded", True),
        503: ("service_unavailable", "service_unavailable", True),
        504: ("timeout_error", "runtime_timeout", True),
    }
    err_type, err_code, retryable = error_mapping.get(
        status_code, ("api_error", "internal_error", False)
    )
    return JSONResponse(
        status_code=status_code,
        content=AIPErrorResponse(
            error=AIPError(
                type=err_type,
                code=err_code,
                message=str(exc.detail),
                request_id=request_id,
                retryable=retryable,
            )
        ).model_dump(),
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc: RequestValidationError):
    request_id = request.headers.get("X-Request-ID") or f"req_{uuid.uuid4().hex[:12]}"
    messages = [
        f"{' -> '.join(str(loc_item) for loc_item in err.get('loc', []))}: {err.get('msg', 'validation error')}"
        for err in exc.errors()
    ]
    return JSONResponse(
        status_code=400,
        content=AIPErrorResponse(
            error=AIPError(
                type="invalid_request_error",
                code="validation_failed",
                message="; ".join(messages),
                request_id=request_id,
                retryable=False,
            )
        ).model_dump(),
    )


app.add_exception_handler(Exception, aip_unhandled_exception_handler)


# Middlewares
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(AdminCIDRMiddleware)
app.add_middleware(PrometheusMetricsMiddleware)
app.add_middleware(QuotaMiddleware)
app.add_middleware(AuthMiddleware)
app.add_middleware(RequestIDMiddleware)


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return Response(status_code=204)


@app.get("/", tags=["Root"], summary="Control Plane Overview")
async def root():
    return {
        "service": "AIP Platform - Control Plane",
        "version": "1.0.0",
        "environment": gateway_settings.environment,
        "architecture": "Domain-Driven Control-Plane Architecture (DCP Pattern)",
        "documentation": {
            "swagger_ui": "/docs",
            "redoc": "/redoc",
            "openapi_spec": "/openapi.json",
        },
        "observability": {
            "liveness": "/health",
            "readiness": "/health/ready",
            "prometheus_metrics": "/metrics",
        },
    }


# 1. Standard AI Routers (OpenAI-compatible)
app.include_router(chat_router)
app.include_router(completions_router)
app.include_router(embeddings_router)
app.include_router(audio_router)
app.include_router(images_router)
app.include_router(moderations_router)
app.include_router(models_router)

# 2. Enterprise Specialized AI Routers
app.include_router(ocr_router)
app.include_router(vision_router)
app.include_router(nlp_router)
app.include_router(nlp_v1_router)

# 3. Async Tasks & Tooling
app.include_router(jobs_router)
app.include_router(predictions_router)
app.include_router(mcp_router)

# 4. Portals & Identity
app.include_router(auth_router)
app.include_router(user_portal_router)
app.include_router(simulations_router)
app.include_router(usage_router)

# Admin Routers
app.include_router(admin_keys_router)
app.include_router(admin_aliases_router)
app.include_router(admin_audit_router)
app.include_router(admin_endpoints_router)
app.include_router(admin_metrics_router)
app.include_router(admin_maintenance_router)
app.include_router(admin_users_router)

# Status & Probes Router
app.include_router(status_router)

# Dynamic Schema Registry Router (DCP Pattern)
from src.schemas.routes import router as schemas_router

app.include_router(schemas_router)

# Hardware & Node Resources Router (DCP Pattern)
from src.resources.routes import router as resources_router

app.include_router(resources_router)
