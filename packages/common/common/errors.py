from __future__ import annotations

import uuid

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from common.models.common import AIPError, AIPErrorResponse


def aip_error_response(
    request: Request, status_code: int, message: str, code: str | None = None
) -> JSONResponse:
    error_map = {
        400: ("invalid_request_error", "bad_request", False),
        401: ("authentication_error", "unauthorized", False),
        403: ("permission_error", "forbidden", False),
        404: ("not_found_error", "not_found", False),
        408: ("timeout_error", "request_timeout", True),
        413: ("invalid_request_error", "payload_too_large", False),
        429: ("rate_limit_error", "rate_limit_exceeded", True),
        502: ("api_error", "upstream_error", True),
        503: ("service_unavailable_error", "service_unavailable", True),
        504: ("timeout_error", "runtime_timeout", True),
    }
    err_type, default_code, retryable = error_map.get(
        status_code, ("api_error", "internal_error", False)
    )
    request_id = request.headers.get("X-Request-ID") or f"req_{uuid.uuid4().hex[:12]}"
    payload = AIPErrorResponse(
        error=AIPError(
            type=err_type,
            code=code or default_code,
            message=message,
            request_id=request_id,
            retryable=retryable,
        )
    )
    return JSONResponse(status_code=status_code, content=payload.model_dump())


async def aip_http_exception_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    return aip_error_response(request, exc.status_code, str(exc.detail))


async def aip_validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    messages = [
        f"{' -> '.join(str(item) for item in error.get('loc', []))}: {error.get('msg', 'validation error')}"
        for error in exc.errors()
    ]
    return aip_error_response(
        request, 400, "; ".join(messages), code="validation_failed"
    )


async def aip_unhandled_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    return aip_error_response(request, 500, "Internal server error")
