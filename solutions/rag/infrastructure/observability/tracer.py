"""
Distributed Tracing and Stage Performance Profiler for AIP Enterprise RAG Solution.
Implements per-request span tracking, stage latency breakdowns, and structured audit logs.
Adheres to Masterclass Layer 5 (Observability - Tracing & Audit Log).
"""

from __future__ import annotations

import contextvars
from dataclasses import dataclass, field
from datetime import datetime, timezone
import logging
import time
from typing import Any, Dict, List, Optional
import uuid

from ...domain.entities import DEFAULT_TENANT_ID

logger = logging.getLogger("aip-rag.observability.tracer")


@dataclass
class TraceSpan:
    name: str
    start_time: float
    end_time: Optional[float] = None
    duration_ms: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None

    def finish(self, error: Optional[str] = None) -> None:
        self.end_time = time.perf_counter()
        self.duration_ms = round((self.end_time - self.start_time) * 1000, 2)
        if error:
            self.error = error


@dataclass
class TraceContext:
    trace_id: str
    request_id: str
    tenant_id: str
    start_time: float
    spans: List[TraceSpan] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def start_span(self, name: str, **metadata: Any) -> TraceSpan:
        span = TraceSpan(name=name, start_time=time.perf_counter(), metadata=metadata)
        self.spans.append(span)
        return span

    def get_stage_durations_ms(self) -> Dict[str, float]:
        """Aggregate durations by stage name."""
        durations: Dict[str, float] = {}
        for s in self.spans:
            if s.duration_ms > 0:
                durations[s.name] = durations.get(s.name, 0.0) + s.duration_ms
        return durations

    def to_audit_dict(self) -> Dict[str, Any]:
        """Convert trace to structured dictionary for audit log and APM export."""
        total_duration_ms = round((time.perf_counter() - self.start_time) * 1000, 2)
        return {
            "trace_id": self.trace_id,
            "request_id": self.request_id,
            "tenant_id": self.tenant_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "total_duration_ms": total_duration_ms,
            "stage_breakdown_ms": self.get_stage_durations_ms(),
            "spans": [
                {
                    "name": s.name,
                    "duration_ms": s.duration_ms,
                    "metadata": s.metadata,
                    "error": s.error,
                }
                for s in self.spans
            ],
            **self.metadata,
        }


# Async-safe task-local storage for active request trace context
_active_trace: contextvars.ContextVar[Optional[TraceContext]] = contextvars.ContextVar(
    "rag_active_trace", default=None
)


class RagTracer:
    """Enterprise RAG Tracer managing active request lifecycle and nested spans."""

    @staticmethod
    def start_trace(
        request_id: Optional[str] = None,
        tenant_id: str = DEFAULT_TENANT_ID,
        trace_id: Optional[str] = None,
    ) -> TraceContext:
        req_id = request_id or uuid.uuid4().hex[:12]
        trc_id = trace_id or f"rag-{uuid.uuid4().hex[:16]}"
        ctx = TraceContext(
            trace_id=trc_id,
            request_id=req_id,
            tenant_id=tenant_id,
            start_time=time.perf_counter(),
        )
        _active_trace.set(ctx)
        return ctx

    @staticmethod
    def get_current_trace() -> Optional[TraceContext]:
        return _active_trace.get()

    @staticmethod
    def clear_trace() -> None:
        _active_trace.set(None)

    @classmethod
    def span(cls, name: str, **metadata: Any):
        """Context manager for tracing an individual execution stage."""
        return _SpanContextManager(name, metadata)


class _SpanContextManager:
    def __init__(self, name: str, metadata: Dict[str, Any]) -> None:
        self.name = name
        self.metadata = metadata
        self.span: Optional[TraceSpan] = None

    def __enter__(self) -> Optional[TraceSpan]:
        ctx = _active_trace.get()
        if ctx:
            self.span = ctx.start_span(self.name, **self.metadata)
        return self.span

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if self.span:
            err_msg = f"{exc_type.__name__}: {exc_val}" if exc_type else None
            self.span.finish(error=err_msg)

    async def __aenter__(self) -> Optional[TraceSpan]:
        return self.__enter__()

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        self.__exit__(exc_type, exc_val, exc_tb)
