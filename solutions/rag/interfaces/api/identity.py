"""
Caller identity resolution for the RAG REST interface.

Identity comes from `request.state`, populated either by the gateway AuthMiddleware (RAG
mounted inside the gateway) or by `InternalCallerMiddleware` (standalone RAG service behind
the gateway). Raw `X-Tenant-ID` / `X-User-Role` headers are only honoured from a caller that
proved it is an internal service (valid X-AIP-Runtime-Token), in TEST_MODE, or when
RAG_TRUST_IDENTITY_HEADERS is enabled for local development.
"""

from __future__ import annotations

import hmac
import os

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from ...config import rag_settings
from ...domain.entities import DEFAULT_TENANT_ID, normalize_tenant_id

ADMIN_ROLES = frozenset({"admin", "system_admin", "superadmin", "knowledge_admin"})
_PUBLIC_PATHS = {"/health", "/health/live", "/health/ready", "/metrics", "/docs", "/openapi.json"}


def _headers_trusted(request: Request) -> bool:
    return (
        bool(getattr(request.state, "internal_caller", False))
        or rag_settings.trust_identity_headers
        or os.getenv("TEST_MODE") == "true"
    )


def extract_tenant(request: Request) -> str:
    tenant = getattr(request.state, "tenant_id", None)
    if not tenant and _headers_trusted(request):
        tenant = request.headers.get("X-Tenant-ID") or request.headers.get("X-Tenant-Id")
    return normalize_tenant_id(tenant)


def extract_role(request: Request) -> str:
    role = getattr(request.state, "role", None)
    if not role and _headers_trusted(request):
        role = request.headers.get("X-User-Role") or request.headers.get("X-Role")
    return (role or "user").strip().lower()


def extract_user(request: Request) -> str:
    # End-user id is supplied by the calling application inside an already authenticated
    # tenant; it scopes session history, not data access.
    return getattr(request.state, "user_id", None) or request.headers.get("X-User-ID") or "default_user"


def is_admin(request: Request) -> bool:
    return extract_role(request) in ADMIN_ROLES


def can_write_tenant(request: Request, tenant_id: str) -> bool:
    """The shared knowledge base (default tenant) is readable by every tenant, so only admins may write to it."""
    return normalize_tenant_id(tenant_id) != DEFAULT_TENANT_ID or is_admin(request) or not rag_settings.enforce_shared_kb_write_acl


class InternalCallerMiddleware(BaseHTTPMiddleware):
    """
    Authenticates service-to-service calls to the standalone RAG API.

    When AIP_RUNTIME_TOKEN is configured, every non-public request must carry a matching
    X-AIP-Runtime-Token; such callers are trusted to forward identity headers.
    """

    async def dispatch(self, request: Request, call_next):
        token = rag_settings.runtime_token
        if request.url.path in _PUBLIC_PATHS or os.getenv("TEST_MODE") == "true":
            return await call_next(request)
        if token:
            supplied = request.headers.get("X-AIP-Runtime-Token", "")
            if not hmac.compare_digest(supplied, token):
                return JSONResponse(status_code=401, content={"detail": "Invalid or missing X-AIP-Runtime-Token"})
            request.state.internal_caller = True
        elif rag_settings.environment.lower() in ("production", "prod") and not rag_settings.trust_identity_headers:
            return JSONResponse(
                status_code=503,
                content={"detail": "AIP_RUNTIME_TOKEN must be configured for the standalone RAG API in production"},
            )
        return await call_next(request)
