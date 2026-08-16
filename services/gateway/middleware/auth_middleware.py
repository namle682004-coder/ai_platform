from common.models.schemas import AIPError, AIPErrorResponse
from gateway.api.admin.endpoints import is_endpoint_enabled
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse


class AuthMiddleware(BaseHTTPMiddleware):
    """
    Control Plane Authentication & Dynamic Export Flag Middleware.
    Validates Bearer API Key & checks if API endpoint is currently enabled by Admin.
    """

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if (
            not path.startswith("/v1/")
            or path.startswith("/v1/auth/")
            or path.startswith("/v1/mcp")
            or path in ["/health", "/docs", "/openapi.json", "/redoc"]
        ):
            return await call_next(request)

        # 1. Dynamic Export Check: Verify if Admin has disabled this API endpoint
        if not is_endpoint_enabled(path):
            error_payload = AIPErrorResponse(
                error=AIPError(
                    type="service_unavailable_error",
                    code="endpoint_disabled",
                    message=f"API endpoint '{path}' is currently disabled by administrator.",
                    request_id=request.headers.get("X-Request-ID"),
                    retryable=True,
                )
            )
            return JSONResponse(status_code=503, content=error_payload.model_dump())

        # 2. Bearer Authentication Check
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            error_payload = AIPErrorResponse(
                error=AIPError(
                    type="authentication_error",
                    code="unauthorized",
                    message="Missing or malformed Bearer API key in Authorization header.",
                    request_id=request.headers.get("X-Request-ID"),
                    retryable=False,
                )
            )
            return JSONResponse(status_code=401, content=error_payload.model_dump())

        raw_api_key = auth_header.replace("Bearer ", "").strip()

        if not raw_api_key or len(raw_api_key) < 8:
            error_payload = AIPErrorResponse(
                error=AIPError(
                    type="authentication_error",
                    code="invalid_api_key",
                    message="Invalid API Key provided.",
                    request_id=request.headers.get("X-Request-ID"),
                    retryable=False,
                )
            )
            return JSONResponse(status_code=401, content=error_payload.model_dump())

        request.state.raw_api_key = raw_api_key
        request.state.tenant_id = "TENANT_DEFAULT"
        request.state.cost_center = "CC_DEFAULT"
        request.state.allowed_aliases = ["*"]
        request.state.rpm_limit = 60
        request.state.tpm_limit = 100000
        request.state.concurrency_limit = 5

        return await call_next(request)
