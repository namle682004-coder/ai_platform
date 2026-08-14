import time
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
from fastapi.responses import Response

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


class PrometheusMetricsMiddleware(BaseHTTPMiddleware):
    """
    Middleware recording Prometheus Metrics for all incoming API Gateway requests.
    """

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if path == "/metrics":
            return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

        AIP_HTTP_INFLIGHT_REQUESTS.inc()
        start_time = time.time()

        try:
            response = await call_next(request)
            duration = time.time() - start_time
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

            return response
        finally:
            AIP_HTTP_INFLIGHT_REQUESTS.dec()
