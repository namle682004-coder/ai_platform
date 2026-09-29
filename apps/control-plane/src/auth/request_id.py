import uuid
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request


class RequestIDMiddleware(BaseHTTPMiddleware):
    """
    SRS Section 3.1: Gateway assigns or propagates X-Request-ID across all requests.
    - Extracts existing X-Request-ID from request headers.
    - If absent, generates standard format: req_<uuid12>.
    - Attaches to request.state.request_id.
    - Always injects X-Request-ID header into outgoing response (success or error).
    """

    async def dispatch(self, request: Request, call_next):
        incoming_id = request.headers.get("X-Request-ID")
        if incoming_id and incoming_id.strip():
            request_id = incoming_id.strip()
        else:
            request_id = f"req_{uuid.uuid4().hex[:12]}"

        request.state.request_id = request_id

        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id

        # SRS Section 6.2: Deprecated Aliases return header X-AIP-Alias-Deprecated: true
        if getattr(request.state, "alias_deprecated", False):
            response.headers["X-AIP-Alias-Deprecated"] = "true"

        return response
