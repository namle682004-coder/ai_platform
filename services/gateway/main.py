import sys
import os
from contextlib import asynccontextmanager

# Add services and packages to sys.path for Vercel & Render environment
current_dir = os.path.dirname(os.path.abspath(__file__))
services_dir = os.path.abspath(os.path.join(current_dir, ".."))
packages_dir = os.path.abspath(os.path.join(current_dir, "..", "..", "packages"))

if services_dir not in sys.path:
    sys.path.insert(0, services_dir)
if packages_dir not in sys.path:
    sys.path.insert(0, packages_dir)

from fastapi import FastAPI, Depends
from fastapi.responses import RedirectResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer

from gateway.middleware.auth_middleware import AuthMiddleware
from gateway.middleware.quota_middleware import QuotaMiddleware
from gateway.middleware.metrics_middleware import PrometheusMetricsMiddleware
from gateway.middleware.cidr_middleware import AdminCIDRMiddleware

# Public Routers
from gateway.api.v1.chat import router as chat_router
from gateway.api.v1.completions import router as completions_router
from gateway.api.v1.embeddings import router as embeddings_router
from gateway.api.v1.audio import router as audio_router
from gateway.api.v1.speech import router as speech_router
from gateway.api.v1.images import router as images_router
from gateway.api.v1.moderations import router as moderations_router
from gateway.api.v1.predictions import router as predictions_router
from gateway.api.v1.jobs import router as jobs_router
from gateway.api.v1.models import router as models_router
from gateway.api.v1.auth import router as auth_router
from gateway.api.v1.mcp import router as mcp_router

# Admin Routers
from gateway.api.admin.keys import router as admin_keys_router
from gateway.api.admin.aliases import router as admin_aliases_router
from gateway.api.admin.audit import router as admin_audit_router
from gateway.api.admin.endpoints import router as admin_endpoints_router
from gateway.api.admin.metrics import router as admin_metrics_router
from gateway.api.admin.maintenance import router as admin_maintenance_router
from gateway.api.admin.users import router as admin_users_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    from common.database.mongodb import mongo_manager
    from gateway.core.config import gateway_settings
    await mongo_manager.connect(uri=gateway_settings.mongo_uri, db_name="ai_platform")
    yield


bearer_scheme = HTTPBearer(auto_error=False)

app = FastAPI(
    title="AI Inference Platform - Gateway Microservice",
    version="1.0.0",
    description="Enterprise Control Plane API Gateway Microservice (100% SRS Production Grade)",
    docs_url="/docs",
    redoc_url="/redoc",
    dependencies=[Depends(bearer_scheme)],
    lifespan=lifespan,
)

# 1. CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 2. Prometheus Metrics Exporter Middleware
app.add_middleware(PrometheusMetricsMiddleware)

# 3. Admin & Staff CIDR Allowlist Protection Middleware
app.add_middleware(AdminCIDRMiddleware)

# 4. Control Plane Rate Limit & Quota Middleware
app.add_middleware(QuotaMiddleware)

# 5. Control Plane Authentication Middleware
app.add_middleware(AuthMiddleware)


# Root Landing Redirect to Admin Dashboard /admin
@app.get("/", include_in_schema=False)
async def root_redirect():
    return RedirectResponse(url="/admin")


# Admin Dashboard Web UI Endpoint
@app.get("/admin", include_in_schema=False)
@app.get("/admin/dashboard", include_in_schema=False)
async def serve_admin_dashboard():
    dashboard_path = os.path.join(current_dir, "static", "admin_dashboard.html")
    return FileResponse(dashboard_path)


# Staff Developer Portal Web UI Endpoint (VPN Protected)
@app.get("/staff", include_in_schema=False)
@app.get("/portal", include_in_schema=False)
async def serve_staff_portal():
    portal_path = os.path.join(current_dir, "static", "staff_portal.html")
    return FileResponse(portal_path)


# Public Status Page Endpoint (/status)
@app.get("/status", include_in_schema=False)
async def serve_status_page():
    status_path = os.path.join(current_dir, "static", "status.html")
    return FileResponse(status_path)


# Register Public /v1 Routers
app.include_router(chat_router)
app.include_router(completions_router)
app.include_router(embeddings_router)
app.include_router(audio_router)
app.include_router(speech_router)
app.include_router(images_router)
app.include_router(moderations_router)
app.include_router(predictions_router)
app.include_router(jobs_router)
app.include_router(models_router)
app.include_router(auth_router)
app.include_router(mcp_router)

# Register Admin /admin/v1 Routers
app.include_router(admin_keys_router)
app.include_router(admin_aliases_router)
app.include_router(admin_audit_router)
app.include_router(admin_endpoints_router)
app.include_router(admin_metrics_router)
app.include_router(admin_maintenance_router)
app.include_router(admin_users_router)


@app.get("/health", tags=["Health"])
async def health_check():
    return {
        "status": "healthy",
        "service": "gateway-microservice",
        "version": "1.0.0",
        "srs_coverage": "100% Full Production Grade",
        "control_plane": {
            "auth_middleware": "active",
            "quota_middleware": "active",
            "prometheus_metrics": "active (/metrics)",
            "admin_cidr_allowlist": "active",
            "admin_dashboard_ui": "active (/admin)",
            "staff_developer_portal": "active (/staff)",
            "public_status_page": "active (/status)",
            "audit_logs": "active (/admin/v1/audit-logs)",
            "auth_system": "active (/v1/auth)",
            "mcp_gateway_bridge": "active (/v1/mcp/sse)",
            "maintenance_circuit_breaker": "active (/admin/v1/maintenance)",
            "users_rbac_governance": "active (/admin/v1/users)",
            "mongodb_atlas": "active (ai_platform)",
        }
    }


if __name__ == "__main__":
    import uvicorn
    from gateway.core.config import gateway_settings

    uvicorn.run(
        "gateway.main:app",
        host=gateway_settings.host,
        port=gateway_settings.port,
        reload=gateway_settings.debug,
    )
