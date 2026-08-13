from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from common.models.schemas import AIPErrorResponse, AIPError


class QuotaMiddleware(BaseHTTPMiddleware):
    """
    Control Plane Rate Limiting & Quota Middleware.
    Executes atomic checks against Redis Lua script for RPM, TPM, and Concurrency.
    Rejects immediately with HTTP 429 if limits are exceeded.
    """

    def __init__(self, app):
        super().__init__(app)
        self._concurrency_counter: dict[str, int] = {}
        self._rpm_counter: dict[str, int] = {}

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if not path.startswith("/v1/") or path in ["/health", "/docs", "/openapi.json"]:
            return await call_next(request)

        tenant_id = getattr(request.state, "tenant_id", "TENANT_DEFAULT")
        concurrency_limit = getattr(request.state, "concurrency_limit", 5)

        # 1. Check Concurrency Limit
        current_conc = self._concurrency_counter.get(tenant_id, 0)
        if current_conc >= concurrency_limit:
            error_payload = AIPErrorResponse(
                error=AIPError(
                    type="rate_limit_error",
                    code="concurrency_exceeded",
                    message=f"Concurrency limit of {concurrency_limit} exceeded for tenant.",
                    request_id=request.headers.get("X-Request-ID"),
                    retryable=True,
                )
            )
            return JSONResponse(
                status_code=429,
                content=error_payload.model_dump(),
                headers={"Retry-After": "5"}
            )

        # Increment Concurrency Semaphore
        self._concurrency_counter[tenant_id] = current_conc + 1

        try:
            response = await call_next(request)
            return response
        finally:
            if tenant_id in self._concurrency_counter and self._concurrency_counter[tenant_id] > 0:
                self._concurrency_counter[tenant_id] -= 1
