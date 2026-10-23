"""
Observability and Prometheus Metrics Middleware for AIP Enterprise RAG Solution API.
Intercepts HTTP requests, handles /metrics endpoint, manages request-scoped trace spans,
and records Prometheus throughput and latency distributions.
"""

from __future__ import annotations

import logging
import time
from typing import Optional
import uuid

from fastapi import Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from starlette.middleware.base import BaseHTTPMiddleware

from ...domain.entities import DEFAULT_TENANT_ID, normalize_tenant_id
from ...infrastructure.observability.metrics import (
    AIP_RAG_ERRORS_TOTAL,
    AIP_RAG_INFLIGHT_REQUESTS,
    AIP_RAG_REQUEST_DURATION_SECONDS,
    AIP_RAG_REQUESTS_TOTAL,
)
from ...infrastructure.observability.tracer import RagTracer

logger = logging.getLogger("aip-rag.api.middleware.observability")


class RagObservabilityMiddleware(BaseHTTPMiddleware):
    """Production Middleware recording Prometheus Metrics and tracing context per RAG request."""

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # 1. Prometheus Scrape Endpoint Fast-Path
        if path in {"/metrics", "/v1/rag/metrics", "/metrics/"}:
            return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

        # 2. Extract Trace, Request, and Tenant Identifiers
        req_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
        raw_tenant = (
            request.headers.get("x-tenant-id")
            or request.query_params.get("tenant_id")
            or DEFAULT_TENANT_ID
        )
        tenant_id = normalize_tenant_id(raw_tenant)

        # 3. Start Distributed Trace Context
        trace_ctx = RagTracer.start_trace(request_id=req_id, tenant_id=tenant_id)
        endpoint = self._normalize_endpoint(path)

        # 4. In-Flight Gauge Tracking
        try:
            AIP_RAG_INFLIGHT_REQUESTS.labels(endpoint=endpoint).inc()
        except Exception:
            pass

        start_time = time.perf_counter()
        try:
            response = await call_next(request)
            duration = time.perf_counter() - start_time
            latency_ms = round(duration * 1000, 2)

            # Record Prometheus Metrics
            try:
                AIP_RAG_REQUESTS_TOTAL.labels(
                    endpoint=endpoint,
                    method=request.method,
                    status=str(response.status_code),
                    tenant_id=tenant_id,
                ).inc()
                AIP_RAG_REQUEST_DURATION_SECONDS.labels(
                    endpoint=endpoint,
                    tenant_id=tenant_id,
                ).observe(duration)
            except Exception as exc:
                logger.debug("Failed recording HTTP Prometheus metrics: %s", exc)

            if response.status_code >= 500:
                try:
                    AIP_RAG_ERRORS_TOTAL.labels(
                        error_type=f"HTTP_{response.status_code}",
                        stage="http_response",
                        tenant_id=tenant_id,
                    ).inc()
                except Exception:
                    pass

            # Inject Standard Tracing & Diagnostic Response Headers
            response.headers["X-Request-ID"] = req_id
            response.headers["X-Trace-ID"] = trace_ctx.trace_id
            response.headers["X-Response-Time-Ms"] = str(latency_ms)

            # Log audit record for slow requests (> 2.0s)
            if duration > 2.0:
                logger.info(
                    "Slow RAG request: %s %s took %.2fs | trace=%s stages=%s",
                    request.method,
                    path,
                    duration,
                    trace_ctx.trace_id,
                    trace_ctx.get_stage_durations_ms(),
                )

            return response
        except Exception as exc:
            duration = time.perf_counter() - start_time
            try:
                AIP_RAG_REQUESTS_TOTAL.labels(
                    endpoint=endpoint,
                    method=request.method,
                    status="500",
                    tenant_id=tenant_id,
                ).inc()
                AIP_RAG_REQUEST_DURATION_SECONDS.labels(
                    endpoint=endpoint,
                    tenant_id=tenant_id,
                ).observe(duration)
                AIP_RAG_ERRORS_TOTAL.labels(
                    error_type=exc.__class__.__name__,
                    stage="http_dispatch",
                    tenant_id=tenant_id,
                ).inc()
            except Exception:
                pass
            raise
        finally:
            try:
                AIP_RAG_INFLIGHT_REQUESTS.labels(endpoint=endpoint).dec()
            except Exception:
                pass
            RagTracer.clear_trace()

    @staticmethod
    def _normalize_endpoint(path: str) -> str:
        """Strip variable path parameters to avoid Prometheus cardinality explosion."""
        if "/chat" in path:
            return "/v1/rag/chat"
        elif "/feedback" in path:
            return "/v1/rag/feedback"
        elif "/documents/upload" in path:
            return "/v1/rag/documents/upload"
        elif "/documents" in path:
            return "/v1/rag/documents"
        elif "/sessions" in path:
            return "/v1/rag/sessions"
        elif "/cache" in path:
            return "/v1/rag/cache"
        return path
