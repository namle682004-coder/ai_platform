import time
import uuid
import asyncio
from datetime import datetime, timezone
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
from fastapi.responses import Response
from common.repositories.api_log_repository import AI_API_LOG_PATHS

# Prometheus Metrics Definitions matching SRS Section 10.1
AIP_HTTP_REQUESTS_TOTAL = Counter(
    "aip_http_requests_total",
    "Total HTTP requests received by API Gateway",
    ["method", "endpoint", "status_code"],
)

AIP_HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "aip_http_request_duration_seconds",
    "HTTP request latency distribution in seconds",
    ["method", "endpoint"],
)

AIP_HTTP_INFLIGHT_REQUESTS = Gauge(
    "aip_http_inflight_requests",
    "Current in-flight HTTP requests being processed",
)

AIP_AUTH_FAILURES_TOTAL = Counter(
    "aip_auth_failures_total",
    "Total API key authentication failures",
)

AIP_RATE_LIMIT_REJECTIONS_TOTAL = Counter(
    "aip_rate_limit_rejections_total",
    "Total requests rejected due to rate limiting or quota",
)

def _should_log_api_call(path: str) -> bool:
    return path in AI_API_LOG_PATHS


class PrometheusMetricsMiddleware(BaseHTTPMiddleware):
    """
    Middleware recording Prometheus Metrics for all requests and API call logs
    for AI inference requests.
    Logs are persisted to MongoDB for the Staff API Report page.
    """

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if path == "/metrics":
            return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

        AIP_HTTP_INFLIGHT_REQUESTS.inc()
        start_time = time.time()
        request_id = str(uuid.uuid4())[:12]

        try:
            response = await call_next(request)
            duration = time.time() - start_time
            latency_ms = round(duration * 1000, 2)

            AIP_HTTP_REQUESTS_TOTAL.labels(
                method=request.method,
                endpoint=path,
                status_code=response.status_code,
            ).inc()
            AIP_HTTP_REQUEST_DURATION_SECONDS.labels(
                method=request.method,
                endpoint=path,
            ).observe(duration)

            if response.status_code == 401:
                AIP_AUTH_FAILURES_TOTAL.inc()
            elif response.status_code == 429:
                AIP_RATE_LIMIT_REJECTIONS_TOTAL.inc()

            # Log API calls to MongoDB (non-blocking, fire-and-forget)
            should_log = _should_log_api_call(path)
            if should_log:
                client_ip = request.client.host if request.client else "unknown"
                log_record = {
                    "request_id": request_id,
                    "method": request.method,
                    "path": path,
                    "status_code": response.status_code,
                    "latency_ms": latency_ms,
                    "client_ip": client_ip,
                    "user_agent": request.headers.get("user-agent", ""),
                    "api_key_prefix": (request.headers.get("authorization", "")[:20] + "...") if request.headers.get("authorization") else None,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                # Fire-and-forget: don't block the response
                asyncio.create_task(_safe_log(log_record))

            return response
        finally:
            AIP_HTTP_INFLIGHT_REQUESTS.dec()


async def _safe_log(log_record: dict):
    """Log API request to MongoDB without blocking or crashing on failure."""
    try:
        from common.repositories.api_log_repository import api_log_repository
        await api_log_repository.log_request(log_record)
    except Exception:
        pass  # Never crash the request pipeline for logging failures
