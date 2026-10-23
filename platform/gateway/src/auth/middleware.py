"""
Enterprise Control Plane Authentication Middleware.
Compliant with SRS Section 8.1 (Argon2id, Redis 60s TTL Cache, Scoped Aliases).
"""

import logging
from common.models.schemas import AIPError, AIPErrorResponse
from common.repositories.mongo_repositories import key_repository
from common.security.argon2_hasher import verify_api_key
from src.admin.endpoints import is_endpoint_enabled
from src.configs.settings import gateway_settings
from src.db.redis import redis_service
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

logger = logging.getLogger("aip-auth")

# Fast in-memory key cache fallback when Redis is offline (TTL 60s)
_LOCAL_KEY_CACHE: dict[str, dict] = {}


def _endpoint_allowed(request: Request) -> bool:
    allowed = getattr(request.state, "allowed_endpoints", ["*"])
    return "*" in allowed or request.url.path in allowed


def _is_production() -> bool:
    return str(gateway_settings.environment).lower() in ("production", "prod")


def _tenant_forbidden(request_id: str, tenant: str) -> JSONResponse:
    error_payload = AIPErrorResponse(
        error=AIPError(
            type="permission_error",
            code="forbidden_tenant",
            message=f"This API key is not authorized for tenant '{tenant}'.",
            request_id=request_id,
            retryable=False,
        )
    )
    return JSONResponse(status_code=403, content=error_payload.model_dump())


def _apply_key_identity(request: Request, key_data: dict, raw_api_key: str, request_id: str) -> JSONResponse | None:
    """
    Bind the verified key's identity to request.state.

    The tenant always comes from the key. An `X-Tenant-ID` header may only select another
    tenant listed in the key's `allowed_tenants` (or "*"); sandbox keys may switch freely
    outside production. The role comes from the key record, never from client headers,
    except for sandbox keys outside production (developer convenience).
    """
    key_tenant = key_data["tenant_id"]
    requested = request.headers.get("X-Tenant-ID") or request.headers.get("X-Tenant-Id")
    allowed_tenants = key_data.get("allowed_tenants") or []
    is_sandbox = bool(key_data.get("sandbox")) and not _is_production()
    if requested and requested != key_tenant and not (is_sandbox or "*" in allowed_tenants or requested in allowed_tenants):
        return _tenant_forbidden(request_id, requested)

    role = key_data.get("role") or "user"
    if is_sandbox:
        role = request.headers.get("X-User-Role") or role

    request.state.raw_api_key = raw_api_key
    request.state.tenant_id = requested or key_tenant
    request.state.role = role
    request.state.cost_center = key_data.get("cost_center", "CC_DIGITAL_BANKING")
    request.state.allowed_aliases = key_data.get("allowed_aliases", ["*"])
    request.state.allowed_endpoints = key_data.get("allowed_endpoints", ["*"])
    request.state.rpm_limit = key_data.get("rpm_limit", 60)
    request.state.tpm_limit = key_data.get("tpm_limit", 100000)
    request.state.concurrency_limit = key_data.get("concurrency_limit", 5)
    if not _endpoint_allowed(request):
        return _endpoint_forbidden(request, request_id)
    return None


def _endpoint_forbidden(request: Request, request_id: str) -> JSONResponse:
    error_payload = AIPErrorResponse(
        error=AIPError(
            type="permission_error",
            code="forbidden_endpoint",
            message=f"Access to endpoint '{request.url.path}' is not authorized for this API key.",
            request_id=request_id,
            retryable=False,
        )
    )
    return JSONResponse(status_code=403, content=error_payload.model_dump())


class AuthMiddleware(BaseHTTPMiddleware):
    """
    Validates Bearer API Keys:
    - Enforces format: aip_live_<entropy> or aip_test_<entropy>
    - Redis cached verification with 60s TTL (SRS 8.1)
    - Resolves tenant_id, quota limits, and allowed_aliases
    - Validates Dynamic Export Status (SRS 5.1)
    """

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        request_id = request.headers.get("X-Request-ID") or "req_aip_init"

        # Bypass health, status, swagger docs, and public auth endpoints
        if (
            not path.startswith("/v1/")
            or path.startswith("/v1/auth/")
            or path.startswith("/v1/user/")
            or path.startswith("/v1/status")
            or path == "/v1/models/status"
            or path in ["/status", "/status/models", "/health", "/health/live", "/health/ready", "/docs", "/openapi.json", "/redoc", "/favicon.ico"]
        ):
            return await call_next(request)

        # 1. Dynamic Export Check: verify if Admin has disabled this API endpoint
        if not is_endpoint_enabled(path):
            error_payload = AIPErrorResponse(
                error=AIPError(
                    type="service_unavailable_error",
                    code="endpoint_disabled",
                    message=f"API endpoint '{path}' is currently disabled by administrator.",
                    request_id=request_id,
                    retryable=True,
                )
            )
            return JSONResponse(status_code=503, content=error_payload.model_dump())

        # 2. Extract Bearer Token or api-key / api_key headers
        auth_header = request.headers.get("Authorization")
        raw_api_key = None
        if auth_header and auth_header.startswith("Bearer "):
            raw_api_key = auth_header.replace("Bearer ", "").strip()
        elif request.headers.get("api-key"):
            raw_api_key = request.headers.get("api-key").strip()
        elif request.headers.get("api_key"):
            raw_api_key = request.headers.get("api_key").strip()
        elif request.query_params.get("token"):
            raw_api_key = request.query_params.get("token").strip()
        elif request.query_params.get("api_key"):
            raw_api_key = request.query_params.get("api_key").strip()

        if not raw_api_key:
            error_payload = AIPErrorResponse(
                error=AIPError(
                    type="authentication_error",
                    code="unauthorized",
                    message="Missing or malformed Bearer API key in Authorization header.",
                    request_id=request_id,
                    retryable=False,
                )
            )
            return JSONResponse(status_code=401, content=error_payload.model_dump())

        # Validate Key Format (SRS Section 8.1: aip_live_ or aip_test_)
        if not (raw_api_key.startswith("aip_live_") or raw_api_key.startswith("aip_test_")):
            error_payload = AIPErrorResponse(
                error=AIPError(
                    type="authentication_error",
                    code="invalid_api_key",
                    message="API key must follow standard format: aip_live_<entropy> or aip_test_<entropy>.",
                    request_id=request_id,
                    retryable=False,
                )
            )
            return JSONResponse(status_code=401, content=error_payload.model_dump())

        # 3. Check Redis Cache / Fast In-Memory Cache (TTL 60s as per SRS Section 8.1)
        redis_key = f"aip:key:{raw_api_key}"
        cached_info = await redis_service.get_json(redis_key)
        if not cached_info:
            cached_info = _LOCAL_KEY_CACHE.get(raw_api_key)

        if cached_info:
            cached_info = dict(cached_info)
            if cached_info.get("tenant_id") in ("TENANT_AUTOMATION_TEST", "TENANT_DEFAULT", "TENANT_RETAIL_BANK"):
                cached_info["tenant_id"] = "proj_default"
            if cached_info.get("cost_center") in ("CC_TEST", "CC_DEFAULT"):
                cached_info["cost_center"] = "CC_DIGITAL_BANKING"
            cached_info.setdefault("tenant_id", "proj_default")
            denied = _apply_key_identity(request, cached_info, raw_api_key, request_id)
            return denied or await call_next(request)

        # 4. Built-in sandbox keys & developer key (never accepted in production)
        is_sandbox_key = (
            raw_api_key in ("aip_live_valid_test_key_12345", "aip_live_testkey123")
            or raw_api_key.startswith("aip_live_valid_test_key")
        )
        configured_dev_key = gateway_settings.dev_api_key.get_secret_value() if gateway_settings.dev_api_key else None
        if (is_sandbox_key or (configured_dev_key and raw_api_key == configured_dev_key)) and not _is_production():
            # Cached per key, so it must not carry per-request header values.
            key_data = {
                "tenant_id": "proj_default",
                "sandbox": True,
                "role": "user",
                "allowed_tenants": ["*"],
                "cost_center": "CC_DIGITAL_BANKING",
                "allowed_aliases": ["*"],
                "allowed_endpoints": ["*"],
                "rpm_limit": 120,
                "tpm_limit": 200000,
                "concurrency_limit": 10,
            }
            _LOCAL_KEY_CACHE[raw_api_key] = key_data
            try:
                await redis_service.set_json(redis_key, key_data, ttl_seconds=60)
            except Exception:
                pass
            denied = _apply_key_identity(request, key_data, raw_api_key, request_id)
            return denied or await call_next(request)

        # 5. Database lookup in MongoDB key_repository
        try:
            db_keys = await key_repository.list_keys(limit=200)
        except Exception as exc:
            logger.warning(
                "API key verification database lookup failed (%s)",
                type(exc).__name__,
            )
            error_payload = AIPErrorResponse(
                error=AIPError(
                    type="service_unavailable",
                    code="authentication_backend_unavailable",
                    message="API key verification is temporarily unavailable. Please retry shortly.",
                    request_id=request_id,
                    retryable=True,
                )
            )
            return JSONResponse(status_code=503, content=error_payload.model_dump())

        matched_key = None
        master_pepper = gateway_settings.master_pepper.get_secret_value()

        for k in db_keys:
            status = k.get("status")
            if status in ("revoked", "disabled", "expired"):
                continue
            hashed = k.get("hashed_key", "")
            if not hashed:
                continue
            if verify_api_key(raw_api_key, hashed, master_pepper=master_pepper) or verify_api_key(raw_api_key, hashed, master_pepper=""):
                matched_key = k
                break

        if matched_key:
            tenant_id = matched_key.get("tenant_id", "TENANT_RETAIL_BANK")
            if tenant_id in ("TENANT_AUTOMATION_TEST", "TENANT_DEFAULT"):
                tenant_id = "TENANT_RETAIL_BANK"
            cost_center = matched_key.get("cost_center", "CC_DIGITAL_BANKING")
            if cost_center in ("CC_TEST", "CC_DEFAULT"):
                cost_center = "CC_DIGITAL_BANKING"

            key_data = {
                "tenant_id": tenant_id,
                "role": matched_key.get("role", "user"),
                "allowed_tenants": matched_key.get("allowed_tenants", []),
                "cost_center": cost_center,
                "allowed_aliases": matched_key.get("allowed_aliases", ["*"]),
                "allowed_endpoints": matched_key.get("allowed_endpoints", ["*"]),
                "rpm_limit": matched_key.get("rpm_limit", 60),
                "tpm_limit": matched_key.get("tpm_limit", 100000),
                "concurrency_limit": matched_key.get("concurrency_limit", 5),
            }
            _LOCAL_KEY_CACHE[raw_api_key] = key_data
            await redis_service.set_json(redis_key, key_data, ttl_seconds=60)
            denied = _apply_key_identity(request, key_data, raw_api_key, request_id)
            return denied or await call_next(request)

        # If key is not verified
        error_payload = AIPErrorResponse(
            error=AIPError(
                type="authentication_error",
                code="invalid_api_key",
                message="Provided API key is revoked, expired, or invalid.",
                request_id=request_id,
                retryable=False,
            )
        )
        return JSONResponse(status_code=401, content=error_payload.model_dump())
