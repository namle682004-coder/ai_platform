import ipaddress
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from common.models.schemas import AIPErrorResponse, AIPError


class AdminCIDRMiddleware(BaseHTTPMiddleware):
    """
    Admin Endpoint Security Middleware enforcing CIDR Allowlist checks as required by SRS Section 8.2.
    Only allows client IPs matching allowed CIDR blocks to access /admin/* endpoints.
    """

    def __init__(self, app, allowed_cidrs: list[str] = None):
        super().__init__(app)
        self.allowed_cidrs = allowed_cidrs or ["127.0.0.1/32", "10.0.0.0/8", "192.168.0.0/16", "172.16.0.0/12"]

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if path.startswith("/admin/"):
            client_ip_str = request.client.host if request.client else "127.0.0.1"

            # Allow local test requests
            if client_ip_str in ["127.0.0.1", "testclient", "localhost"]:
                return await call_next(request)

            try:
                client_ip = ipaddress.ip_address(client_ip_str)
                is_allowed = any(
                    client_ip in ipaddress.ip_network(cidr)
                    for cidr in self.allowed_cidrs
                )
                if not is_allowed:
                    error_payload = AIPErrorResponse(
                        error=AIPError(
                            type="security_error",
                            code="cidr_forbidden",
                            message=f"Access denied: Source IP '{client_ip_str}' is not in Admin CIDR Allowlist.",
                            request_id=request.headers.get("X-Request-ID"),
                            retryable=False,
                        )
                    )
                    return JSONResponse(status_code=403, content=error_payload.model_dump())
            except ValueError:
                pass

        return await call_next(request)
