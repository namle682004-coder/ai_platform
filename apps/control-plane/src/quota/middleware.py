import logging
from typing import Optional
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from common.models.schemas import AIPError, AIPErrorResponse
from .enforcer import quota_enforcer, QuotaEnforcer

logger = logging.getLogger("aip-rate-limit")

_DEFAULT_RPM = 60
_DEFAULT_CONCURRENCY = 5


class QuotaMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, enforcer: Optional[QuotaEnforcer] = None):
        super().__init__(app)
        self.enforcer = enforcer or quota_enforcer

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if (
            not path.startswith("/v1/")
            or path.startswith("/v1/auth/")
            or path.startswith("/v1/mcp")
            or path in ["/health", "/docs", "/openapi.json", "/favicon.ico"]
        ):
            return await call_next(request)

        # 1. Resolve raw api key & bucket
        raw_api_key = getattr(request.state, "raw_api_key", None)
        if not raw_api_key:
            auth_header = request.headers.get("Authorization")
            if auth_header and auth_header.startswith("Bearer "):
                raw_api_key = auth_header[7:].strip()

        client_host = request.client.host if request.client else "unknown"
        bucket = self.enforcer.resolve_bucket(raw_api_key, client_host)

        limit = getattr(request.state, "rpm_limit", _DEFAULT_RPM)
        concurrency_limit = getattr(request.state, "concurrency_limit", _DEFAULT_CONCURRENCY)
        request_id = request.headers.get("X-Request-ID") or getattr(request.state, "request_id", "req_rate_limit")

        # 2. Atomic Redis Lua Check (Rate Limit, Quota & Concurrency in single call - SRS 3.1)
        allowed, reason, rate_headers, current_conc = await self.enforcer.check_atomic_quota(
            bucket=bucket,
            rpm_limit=limit,
            concurrency_limit=concurrency_limit,
        )

        if not allowed:
            if reason == "rate_limit_store_unavailable":
                error_payload = AIPErrorResponse(
                    error=AIPError(
                        type="service_unavailable",
                        code="rate_limit_store_unavailable",
                        message="Rate-limit service is temporarily unavailable.",
                        request_id=request_id,
                        retryable=True,
                    )
                )
                return JSONResponse(
                    status_code=503,
                    content=error_payload.model_dump(),
                    headers={"Retry-After": "5", "X-Request-ID": request_id},
                )
            if reason == "concurrency_exceeded":
                error_payload = AIPErrorResponse(
                    error=AIPError(
                        type="rate_limit_error",
                        code="concurrency_exceeded",
                        message=f"Concurrency limit of {concurrency_limit} in-flight requests exceeded.",
                        request_id=request_id,
                        retryable=True,
                    )
                )
                return JSONResponse(
                    status_code=429,
                    content=error_payload.model_dump(),
                    headers={"Retry-After": "5", "X-Request-ID": request_id},
                )
            elif reason == "quota_exceeded":
                error_payload = AIPErrorResponse(
                    error=AIPError(
                        type="rate_limit_error",
                        code="quota_exceeded",
                        message="Tenant monthly quota exceeded. Please contact administrator or wait until reset.",
                        request_id=request_id,
                        retryable=True,
                    )
                )
                return JSONResponse(
                    status_code=429,
                    headers={**rate_headers, "Retry-After": "60", "X-Request-ID": request_id},
                    content=error_payload.model_dump(),
                )
            else:
                # Default rate_limit_exceeded (SRS Section 3.4)
                reset_seconds = rate_headers.get("X-RateLimit-Reset", "60")
                error_payload = AIPErrorResponse(
                    error=AIPError(
                        type="rate_limit_error",
                        code="rate_limit_exceeded",
                        message=f"Rate limit of {limit} RPM exceeded. Retry after {reset_seconds} seconds.",
                        request_id=request_id,
                        retryable=True,
                    )
                )
                return JSONResponse(
                    status_code=429,
                    headers={
                        **rate_headers,
                        "Retry-After": str(reset_seconds),
                        "X-Request-ID": request_id,
                    },
                    content=error_payload.model_dump(),
                )

        try:
            response = await call_next(request)
            for h_name, h_val in rate_headers.items():
                response.headers[h_name] = h_val
            return response
        finally:
            self.enforcer.release_concurrency(bucket)
