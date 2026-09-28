"""Authentication boundary for private data-plane runtime services."""

from __future__ import annotations

import os
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from common.errors import aip_error_response


class RuntimeAuthMiddleware(BaseHTTPMiddleware):
    """Require the shared service token when configured, otherwise a Bearer header."""

    async def dispatch(self, request: Request, call_next):
        if os.getenv("TEST_MODE") == "true":
            return await call_next(request)

        if request.url.path in {
            "/health",
            "/health/live",
            "/health/ready",
            "/docs",
            "/openapi.json",
        }:
            return await call_next(request)

        configured_token = os.getenv("AIP_RUNTIME_TOKEN")
        if configured_token:
            supplied_token = request.headers.get("X-AIP-Runtime-Token")
            if supplied_token != configured_token:
                return aip_error_response(request, 401, "Invalid runtime service token")
        elif not request.headers.get("Authorization", "").startswith("Bearer "):
            return aip_error_response(request, 401, "Bearer API key required")

        return await call_next(request)
