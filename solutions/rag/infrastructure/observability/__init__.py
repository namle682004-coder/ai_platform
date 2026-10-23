"""
Observability Package for AIP Enterprise RAG Solution.
Exports Prometheus metrics, concrete adapter, tracing context, and measurement utilities.
"""

from .metrics import (
    AIP_RAG_CACHE_OPERATIONS_TOTAL,
    AIP_RAG_ERRORS_TOTAL,
    AIP_RAG_GROUNDEDNESS_SCORE,
    AIP_RAG_INFLIGHT_REQUESTS,
    AIP_RAG_INGESTION_CHUNKS_TOTAL,
    AIP_RAG_INGESTION_DURATION_SECONDS,
    AIP_RAG_REQUEST_DURATION_SECONDS,
    AIP_RAG_REQUESTS_TOTAL,
    AIP_RAG_RETRIEVED_CHUNKS,
    AIP_RAG_STAGE_DURATION_SECONDS,
    AIP_RAG_TOKENS_TOTAL,
    PrometheusObservabilityAdapter,
    StageMeasure,
    get_observability,
    measure_stage,
    rag_observability,
)
from .tracer import RagTracer, TraceContext, TraceSpan

__all__ = [
    "AIP_RAG_REQUESTS_TOTAL",
    "AIP_RAG_REQUEST_DURATION_SECONDS",
    "AIP_RAG_STAGE_DURATION_SECONDS",
    "AIP_RAG_INFLIGHT_REQUESTS",
    "AIP_RAG_CACHE_OPERATIONS_TOTAL",
    "AIP_RAG_TOKENS_TOTAL",
    "AIP_RAG_RETRIEVED_CHUNKS",
    "AIP_RAG_GROUNDEDNESS_SCORE",
    "AIP_RAG_ERRORS_TOTAL",
    "AIP_RAG_INGESTION_CHUNKS_TOTAL",
    "AIP_RAG_INGESTION_DURATION_SECONDS",
    "PrometheusObservabilityAdapter",
    "rag_observability",
    "get_observability",
    "StageMeasure",
    "measure_stage",
    "RagTracer",
    "TraceContext",
    "TraceSpan",
]
