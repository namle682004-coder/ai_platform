"""
Production Prometheus Metrics and Telemetry Adapter for AIP Enterprise RAG Solution.
Adheres to Masterclass Layer 5 (Observability - Monitoring, Evaluation, Audit).
Implements domain ObservabilityPort with strict multi-tenant label isolation.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

from ...domain.entities import DEFAULT_TENANT_ID, normalize_tenant_id
from ...domain.ports import ObservabilityPort
from .tracer import RagTracer

logger = logging.getLogger("aip-rag.observability.metrics")

# ==============================================================================
# Prometheus Metrics Definitions (Enterprise RAG Monitoring)
# ==============================================================================

AIP_RAG_REQUESTS_TOTAL = Counter(
    "aip_rag_requests_total",
    "Total HTTP requests received by RAG API",
    ["endpoint", "method", "status", "tenant_id"],
)

AIP_RAG_REQUEST_DURATION_SECONDS = Histogram(
    "aip_rag_request_duration_seconds",
    "Total RAG end-to-end request duration in seconds",
    ["endpoint", "tenant_id"],
    buckets=[0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 3.0, 5.0, 10.0, 20.0, 60.0],
)

AIP_RAG_STAGE_DURATION_SECONDS = Histogram(
    "aip_rag_stage_duration_seconds",
    "Duration of individual RAG pipeline execution stages in seconds",
    ["stage", "tenant_id"],
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0],
)

AIP_RAG_INFLIGHT_REQUESTS = Gauge(
    "aip_rag_inflight_requests",
    "Current active in-flight requests processed by RAG engine",
    ["endpoint"],
)

AIP_RAG_CACHE_OPERATIONS_TOTAL = Counter(
    "aip_rag_cache_operations_total",
    "RAG multi-tier cache operations (exact, semantic, kv_prefix)",
    ["cache_type", "result", "tenant_id"],
)

AIP_RAG_TOKENS_TOTAL = Counter(
    "aip_rag_tokens_total",
    "Total LLM token consumption in RAG pipeline",
    ["model", "type", "tenant_id"],
)

AIP_RAG_RETRIEVED_CHUNKS = Histogram(
    "aip_rag_retrieved_chunks_count",
    "Distribution of candidate chunks retrieved before reranking",
    ["retriever_type", "tenant_id"],
    buckets=[1, 2, 5, 10, 15, 20, 30, 50, 100],
)

AIP_RAG_GROUNDEDNESS_SCORE = Histogram(
    "aip_rag_groundedness_score",
    "Anti-hallucination / groundedness verification score distribution [0.0 - 1.0]",
    ["tenant_id"],
    buckets=[0.0, 0.2, 0.4, 0.6, 0.7, 0.8, 0.9, 1.0],
)

AIP_RAG_ERRORS_TOTAL = Counter(
    "aip_rag_errors_total",
    "Total errors categorized by error type and pipeline stage",
    ["error_type", "stage", "tenant_id"],
)

AIP_RAG_INGESTION_CHUNKS_TOTAL = Counter(
    "aip_rag_ingestion_chunks_total",
    "Total document chunks created during ingestion",
    ["tenant_id", "status"],
)

AIP_RAG_INGESTION_DURATION_SECONDS = Histogram(
    "aip_rag_ingestion_duration_seconds",
    "Total document ingestion and parsing duration in seconds",
    ["tenant_id", "file_type"],
    buckets=[0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 180.0],
)


# ==============================================================================
# Concrete Adapter Implementation
# ==============================================================================

class PrometheusObservabilityAdapter(ObservabilityPort):
    """Production Prometheus Observability Adapter implementing ObservabilityPort."""

    def record_request(
        self,
        endpoint: str,
        method: str,
        status_code: int,
        duration: float,
        tenant_id: str = DEFAULT_TENANT_ID,
    ) -> None:
        t_id = normalize_tenant_id(tenant_id)
        status_str = str(status_code)
        try:
            AIP_RAG_REQUESTS_TOTAL.labels(
                endpoint=endpoint,
                method=method,
                status=status_str,
                tenant_id=t_id,
            ).inc()
            AIP_RAG_REQUEST_DURATION_SECONDS.labels(
                endpoint=endpoint,
                tenant_id=t_id,
            ).observe(duration)
        except Exception as exc:
            logger.debug("Failed recording request metrics: %s", exc)

    def record_stage_latency(
        self,
        stage: str,
        duration: float,
        tenant_id: str = DEFAULT_TENANT_ID,
    ) -> None:
        t_id = normalize_tenant_id(tenant_id)
        try:
            AIP_RAG_STAGE_DURATION_SECONDS.labels(
                stage=stage,
                tenant_id=t_id,
            ).observe(duration)
        except Exception as exc:
            logger.debug("Failed recording stage latency metrics: %s", exc)

    def record_cache_op(
        self,
        cache_type: str,
        result: str,
        tenant_id: str = DEFAULT_TENANT_ID,
    ) -> None:
        t_id = normalize_tenant_id(tenant_id)
        try:
            AIP_RAG_CACHE_OPERATIONS_TOTAL.labels(
                cache_type=cache_type,
                result=result,
                tenant_id=t_id,
            ).inc()
        except Exception as exc:
            logger.debug("Failed recording cache operation metrics: %s", exc)

    def record_tokens(
        self,
        model: str,
        token_type: str,
        count: int,
        tenant_id: str = DEFAULT_TENANT_ID,
    ) -> None:
        if count <= 0:
            return
        t_id = normalize_tenant_id(tenant_id)
        clean_model = model or "default"
        try:
            AIP_RAG_TOKENS_TOTAL.labels(
                model=clean_model,
                type=token_type,
                tenant_id=t_id,
            ).inc(count)
        except Exception as exc:
            logger.debug("Failed recording token metrics: %s", exc)

    def record_retrieval(
        self,
        retriever_type: str,
        chunk_count: int,
        tenant_id: str = DEFAULT_TENANT_ID,
    ) -> None:
        t_id = normalize_tenant_id(tenant_id)
        try:
            AIP_RAG_RETRIEVED_CHUNKS.labels(
                retriever_type=retriever_type,
                tenant_id=t_id,
            ).observe(max(0, chunk_count))
        except Exception as exc:
            logger.debug("Failed recording retrieval metrics: %s", exc)

    def record_groundedness(
        self,
        score: float,
        tenant_id: str = DEFAULT_TENANT_ID,
    ) -> None:
        t_id = normalize_tenant_id(tenant_id)
        clamped_score = max(0.0, min(1.0, float(score)))
        try:
            AIP_RAG_GROUNDEDNESS_SCORE.labels(
                tenant_id=t_id,
            ).observe(clamped_score)
        except Exception as exc:
            logger.debug("Failed recording groundedness score metrics: %s", exc)

    def record_error(
        self,
        error_type: str,
        stage: str,
        tenant_id: str = DEFAULT_TENANT_ID,
    ) -> None:
        t_id = normalize_tenant_id(tenant_id)
        try:
            AIP_RAG_ERRORS_TOTAL.labels(
                error_type=error_type,
                stage=stage,
                tenant_id=t_id,
            ).inc()
        except Exception as exc:
            logger.debug("Failed recording error metrics: %s", exc)

    def record_ingestion(
        self,
        tenant_id: str,
        status: str,
        duration: float,
        chunk_count: int,
        file_type: str = "unknown",
    ) -> None:
        t_id = normalize_tenant_id(tenant_id)
        try:
            AIP_RAG_INGESTION_CHUNKS_TOTAL.labels(
                tenant_id=t_id,
                status=status,
            ).inc(max(0, chunk_count))
            AIP_RAG_INGESTION_DURATION_SECONDS.labels(
                tenant_id=t_id,
                file_type=file_type or "unknown",
            ).observe(duration)
        except Exception as exc:
            logger.debug("Failed recording ingestion metrics: %s", exc)


# Global singleton instance
rag_observability: ObservabilityPort = PrometheusObservabilityAdapter()


def get_observability() -> ObservabilityPort:
    """Factory dependency provider for Clean Architecture DI."""
    return rag_observability


# ==============================================================================
# Dual Synchronous & Asynchronous Stage Measurement Context Manager
# ==============================================================================

class StageMeasure:
    """
    Context manager supporting both `with measure_stage(...)` and `async with measure_stage(...)`.
    Accurately records execution time to Prometheus Histogram and active TraceSpan.
    """

    def __init__(
        self,
        stage: str,
        tenant_id: str = DEFAULT_TENANT_ID,
        obs: Optional[ObservabilityPort] = None,
        **metadata: Any,
    ) -> None:
        self.stage = stage
        self.tenant_id = normalize_tenant_id(tenant_id)
        self.obs = obs or rag_observability
        self.metadata = metadata
        self._start_time: float = 0.0
        self._trace_cm = None

    def __enter__(self) -> "StageMeasure":
        self._start_time = time.perf_counter()
        self._trace_cm = RagTracer.span(self.stage, tenant_id=self.tenant_id, **self.metadata)
        self._trace_cm.__enter__()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        duration = time.perf_counter() - self._start_time
        try:
            self.obs.record_stage_latency(self.stage, duration, self.tenant_id)
            if exc_type is not None:
                self.obs.record_error(
                    error_type=exc_type.__name__,
                    stage=self.stage,
                    tenant_id=self.tenant_id,
                )
        finally:
            if self._trace_cm:
                self._trace_cm.__exit__(exc_type, exc_val, exc_tb)

    async def __aenter__(self) -> "StageMeasure":
        return self.__enter__()

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        self.__exit__(exc_type, exc_val, exc_tb)


def measure_stage(
    stage: str,
    tenant_id: str = DEFAULT_TENANT_ID,
    obs: Optional[ObservabilityPort] = None,
    **metadata: Any,
) -> StageMeasure:
    """Convenience helper creating a dual sync/async stage measurement context."""
    return StageMeasure(stage=stage, tenant_id=tenant_id, obs=obs, **metadata)
