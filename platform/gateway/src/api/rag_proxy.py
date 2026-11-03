"""
Gateway pass-through for the standalone Enterprise RAG service (solutions/rag, port 8010).

All RAG logic (chat, sessions, knowledge base, ingestion) lives in the RAG service. The gateway
keeps authentication, tenant authorization and quota, then forwards /v1/rag/* and /v1/knowledge/*
with the verified identity as headers. The RAG service trusts those identity headers only from a
caller presenting X-AIP-Runtime-Token, so client-supplied identity headers are never forwarded.
"""

from __future__ import annotations

import logging
from typing import Optional

import httpx
from common.models.schemas import AIPError, AIPErrorResponse
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.background import BackgroundTask
from src.configs.settings import gateway_settings

logger = logging.getLogger("aip-api.rag-proxy")

router = APIRouter(tags=["Knowledge & RAG"])

_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE"]

# Client headers passed through unchanged; identity headers are set from request.state instead.
_FORWARDED_REQUEST_HEADERS = ("content-type", "accept", "authorization", "x-request-id", "last-event-id")

_HOP_BY_HOP_HEADERS = frozenset(
    {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te", "trailers", "transfer-encoding", "upgrade"}
)

_client: Optional[httpx.AsyncClient] = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(
            timeout=httpx.Timeout(gateway_settings.rag_proxy_timeout_seconds, connect=5.0),
        )
    return _client


def _upstream_headers(request: Request) -> dict[str, str]:
    headers = {name: value for name in _FORWARDED_REQUEST_HEADERS if (value := request.headers.get(name))}

    tenant_id = getattr(request.state, "tenant_id", None)
    role = getattr(request.state, "role", None)
    user_id = getattr(request.state, "user_id", None) or request.headers.get("X-User-ID")
    if tenant_id:
        headers["X-Tenant-ID"] = str(tenant_id)
    if role:
        headers["X-User-Role"] = str(role)
    if user_id:
        headers["X-User-ID"] = str(user_id)
    if gateway_settings.runtime_token:
        headers["X-AIP-Runtime-Token"] = gateway_settings.runtime_token.get_secret_value()
    return headers


def _error(status_code: int, error_type: str, code: str, message: str, request: Request) -> JSONResponse:
    body = AIPErrorResponse(
        error=AIPError(
            type=error_type,
            code=code,
            message=message,
            request_id=getattr(request.state, "request_id", None) or request.headers.get("X-Request-ID") or "req_rag_proxy",
            retryable=True,
        )
    )
    return JSONResponse(status_code=status_code, content=body.model_dump())


@router.api_route("/v1/rag/{path:path}", methods=_METHODS, include_in_schema=False)
@router.api_route("/v1/knowledge/{path:path}", methods=_METHODS, include_in_schema=False)
async def forward_to_rag_service(request: Request, path: str):
    target_url = f"{gateway_settings.rag_service_url.rstrip('/')}{request.url.path}"
    client = _get_client()
    upstream_request = client.build_request(
        request.method,
        target_url,
        params=request.query_params,
        headers=_upstream_headers(request),
        content=await request.body(),
    )

    try:
        upstream = await client.send(upstream_request, stream=True)
    except httpx.TimeoutException as exc:
        logger.warning("RAG service timed out for %s %s: %s", request.method, request.url.path, exc)
        return _error(504, "timeout_error", "rag_service_timeout", "Enterprise RAG service timed out.", request)
    except httpx.HTTPError as exc:
        logger.warning("RAG service unreachable at %s: %s", gateway_settings.rag_service_url, exc)
        return _error(503, "server_error", "rag_service_unavailable", "Enterprise RAG service is unavailable.", request)

    response_headers = {k: v for k, v in upstream.headers.items() if k.lower() not in _HOP_BY_HOP_HEADERS}
    # Raw bytes keep SSE chunks (POST /v1/rag/chat with stream=true) flowing as they arrive.
    return StreamingResponse(
        upstream.aiter_raw(),
        status_code=upstream.status_code,
        headers=response_headers,
        background=BackgroundTask(upstream.aclose),
    )
