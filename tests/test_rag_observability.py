"""
Production Test Suite for AIP Enterprise RAG Observability & Prometheus Telemetry.
Validates:
1. Prometheus Metrics Definitions & Registry Registration (Masterclass Layer 5).
2. PrometheusObservabilityAdapter method execution and multi-tenant label normalization.
3. Synchronous & Asynchronous Stage Measurement Context Managers (`measure_stage`).
4. Distributed Request Tracing (`RagTracer`, `TraceContext`, `TraceSpan`, audit dictionary).
5. Observability Middleware (`/metrics` scrape endpoint, request timing, diagnostic response headers).
6. Pure Clean Architecture compliance (NullObservabilityAdapter fallbacks).
"""

import asyncio
import time
from fastapi.testclient import TestClient
from prometheus_client import generate_latest

from solutions.rag.domain.ports import (
    NullObservabilityAdapter,
    ObservabilityPort,
)
from solutions.rag.infrastructure.observability import (
    PrometheusObservabilityAdapter,
    RagTracer,
    measure_stage,
)
from solutions.rag.main import app


def test_prometheus_metrics_exposed():
    """Verify all 11 enterprise RAG Prometheus metrics are registered and exportable."""
    body = generate_latest().decode("utf-8")
    expected_metrics = [
        "aip_rag_requests_total",
        "aip_rag_request_duration_seconds",
        "aip_rag_stage_duration_seconds",
        "aip_rag_inflight_requests",
        "aip_rag_cache_operations_total",
        "aip_rag_tokens_total",
        "aip_rag_retrieved_chunks_count",
        "aip_rag_groundedness_score",
        "aip_rag_errors_total",
        "aip_rag_ingestion_chunks_total",
        "aip_rag_ingestion_duration_seconds",
    ]
    for metric_name in expected_metrics:
        assert metric_name in body, f"Expected metric '{metric_name}' in Prometheus export"


def test_observability_adapter_methods():
    """Verify concrete adapter executes all metric operations with tenant normalization."""
    adapter = PrometheusObservabilityAdapter()

    # 1. Request metrics
    adapter.record_request("/v1/rag/chat", "POST", 200, 0.42, tenant_id="tenant_alpha")

    # 2. Stage latency
    adapter.record_stage_latency("rewrite", 0.05, tenant_id="tenant_alpha")
    adapter.record_stage_latency("retrieval_dense", 0.12, tenant_id="tenant_alpha")
    adapter.record_stage_latency("retrieval_sparse", 0.08, tenant_id="tenant_alpha")
    adapter.record_stage_latency("rerank", 0.09, tenant_id="tenant_alpha")
    adapter.record_stage_latency("llm_generate", 0.25, tenant_id="tenant_alpha")

    # 3. Cache operations
    adapter.record_cache_op("exact", "hit", tenant_id="tenant_alpha")
    adapter.record_cache_op("kv_prefix", "hit", tenant_id="tenant_alpha")
    adapter.record_cache_op("semantic", "miss", tenant_id="tenant_alpha")

    # 4. Token usage
    adapter.record_tokens("qwen-2.5-7b", "prompt", 512, tenant_id="tenant_alpha")
    adapter.record_tokens("qwen-2.5-7b", "completion", 128, tenant_id="tenant_alpha")
    adapter.record_tokens("qwen-2.5-7b", "cached_prefix", 256, tenant_id="tenant_alpha")

    # 5. Retrieval & Groundedness
    adapter.record_retrieval("hybrid", 16, tenant_id="tenant_alpha")
    adapter.record_groundedness(0.85, tenant_id="tenant_alpha")

    # 6. Errors & Ingestion
    adapter.record_error("TimeoutError", "llm_generate", tenant_id="tenant_alpha")
    adapter.record_ingestion("tenant_alpha", "INDEXED", 1.25, 42, file_type="pdf")

    # Verify scraped output reflects these entries
    body = generate_latest().decode("utf-8")
    assert 'tenant_id="tenant_alpha"' in body
    assert 'stage="rewrite"' in body
    assert 'stage="retrieval_dense"' in body
    assert 'type="cached_prefix"' in body
    assert 'cache_type="kv_prefix"' in body


def test_stage_measure_context_managers():
    """Verify both synchronous and asynchronous stage measurement context managers."""
    # 1. Sync context manager
    with measure_stage("test_sync_stage", tenant_id="tenant_beta"):
        time.sleep(0.01)

    # 2. Async context manager
    async def run_async_stage():
        async with measure_stage("test_async_stage", tenant_id="tenant_beta"):
            await asyncio.sleep(0.01)

    asyncio.run(run_async_stage())

    body = generate_latest().decode("utf-8")
    assert 'stage="test_sync_stage"' in body
    assert 'stage="test_async_stage"' in body


def test_rag_tracer_lifecycle():
    """Verify distributed tracer creates context, records nested spans, and exports audit dict."""
    ctx = RagTracer.start_trace(request_id="req-test-123", tenant_id="tenant_gamma")
    assert ctx.request_id == "req-test-123"
    assert ctx.tenant_id == "tenant_gamma"
    assert ctx.trace_id.startswith("rag-")

    # Trace nested execution
    with RagTracer.span("query_rewriter", mode="speculative"):
        time.sleep(0.005)

    with RagTracer.span("hybrid_retriever", top_k=20):
        time.sleep(0.005)

    # Convert to structured audit dict
    audit = ctx.to_audit_dict()
    assert audit["request_id"] == "req-test-123"
    assert audit["tenant_id"] == "tenant_gamma"
    assert "stage_breakdown_ms" in audit
    assert "query_rewriter" in audit["stage_breakdown_ms"]
    assert "hybrid_retriever" in audit["stage_breakdown_ms"]
    assert len(audit["spans"]) == 2

    RagTracer.clear_trace()
    assert RagTracer.get_current_trace() is None


def test_observability_middleware_metrics_endpoint():
    """Verify Prometheus scrape endpoint /metrics returns 200 with standard content type."""
    client = TestClient(app)

    # 1. Test root /metrics endpoint
    res = client.get("/metrics")
    assert res.status_code == 200
    assert "text/plain" in res.headers["content-type"]
    assert "aip_rag_requests_total" in res.text

    # 2. Test routed /v1/rag/metrics endpoint
    res2 = client.get("/v1/rag/metrics")
    assert res2.status_code == 200
    assert "aip_rag_requests_total" in res2.text


def test_observability_middleware_diagnostic_headers():
    """Verify middleware injects X-Request-ID, X-Trace-ID, and X-Response-Time-Ms headers."""
    client = TestClient(app)

    # Any valid request path (e.g. GET /metrics or 404 test path)
    client.get("/metrics", headers={"X-Request-ID": "custom-req-999"})
    # Notice /metrics is intercepted by fast-path, so let's hit a normal route
    res_normal = client.get("/v1/rag/sessions", headers={
        "X-Request-ID": "custom-req-777",
        "X-Tenant-ID": "tenant_custom",
    })
    assert "X-Request-ID" in res_normal.headers
    assert res_normal.headers["X-Request-ID"] == "custom-req-777"
    assert "X-Trace-ID" in res_normal.headers
    assert "X-Response-Time-Ms" in res_normal.headers
    assert float(res_normal.headers["X-Response-Time-Ms"]) >= 0.0


def test_null_observability_adapter_clean_architecture():
    """Verify NullObservabilityAdapter satisfies ObservabilityPort with zero exceptions."""
    null_obs = NullObservabilityAdapter()
    assert isinstance(null_obs, ObservabilityPort)

    null_obs.record_request("/test", "GET", 200, 0.1)
    null_obs.record_stage_latency("rewrite", 0.01)
    null_obs.record_cache_op("exact", "hit")
    null_obs.record_tokens("model", "prompt", 100)
    null_obs.record_retrieval("dense", 5)
    null_obs.record_groundedness(0.9)
    null_obs.record_error("TestErr", "stage")
    null_obs.record_ingestion("tenant", "ok", 1.0, 10, "txt")
