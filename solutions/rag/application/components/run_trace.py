"""
Per-turn pipeline trace: what every stage of one chat turn received and produced.

A wrong answer is diagnosed from its trace instead of by re-running scripts: the query analysis
(intent, rewritten question), the retrieval and rerank candidates with their scores and the
identifiers they contain, the evidence-gate decision, the passages sent to the model, the raw
generation, the sentences removed by verification and the corrective regeneration. The
evaluation harness reads the same record to attribute a failure to the stage that caused it.

The recorder is task-local (contextvars), so pipeline helpers record without threading an object
through every call; outside a traced turn every call is a no-op.
"""

from __future__ import annotations

import contextvars
import random
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, Iterator, List, Optional, Sequence

from common.chunking import PiiSanitizer

from .context_selector import candidate_key, payload_of
from .lexical_evidence import candidate_heading, candidate_text, extract_identifiers

TRACE_SCHEMA_VERSION = 1
# Identifiers kept per chunk reference (enough to locate gold evidence by code).
MAX_IDS_PER_CHUNK = 40
# Answer-level outcomes that are always kept, whatever the sampling rate (tail-based sampling).
ALWAYS_KEEP_STAGES = ("correction", "refusal_recovery", "error")
# Stage fields holding text the user typed or the model generated (PII-masked when stored).
USER_TEXT_FIELDS = ("query", "standalone_query", "sparse_query", "user_content", "raw_answer")


def new_trace_id() -> str:
    return f"rag-{uuid.uuid4().hex[:16]}"


def chunk_ref(c: Any, score: Optional[float] = None, text_chars: int = 0) -> Dict[str, Any]:
    """Compact, JSON-safe reference to a retrieved chunk."""
    p = payload_of(c)
    text = candidate_text(c)
    ref: Dict[str, Any] = {
        "doc_id": str(p.get("doc_id") or ""),
        "title": str(p.get("title") or "")[:160],
        "chunk_index": int(p.get("chunk_index", 0) or 0),
        "heading": (candidate_heading(c) or "")[:160],
        "ids": extract_identifiers(text)[:MAX_IDS_PER_CHUNK],
    }
    if score is None and isinstance(c, dict):
        score = c.get("score")
    if score is not None:
        ref["score"] = round(float(score or 0.0), 4)
    if text_chars > 0:
        ref["text"] = text[:text_chars]
    return ref


def chunk_refs(
    chunks: Iterable[Any],
    scores: Optional[Dict[str, float]] = None,
    text_chars: int = 0,
    limit: int = 64,
) -> List[Dict[str, Any]]:
    out = []
    for c in list(chunks or [])[:limit]:
        score = scores.get(candidate_key(c)) if scores is not None else None
        out.append(chunk_ref(c, score=score, text_chars=text_chars))
    return out


@dataclass
class TurnTrace:
    trace_id: str
    tenant_id: str
    session_id: str
    user_id: str
    query: str
    endpoint: str = "chat"
    model: str = ""
    started: float = field(default_factory=time.perf_counter)
    created_at: float = field(default_factory=time.time)
    stages: List[Dict[str, Any]] = field(default_factory=list)
    outcome: Dict[str, Any] = field(default_factory=dict)
    config: Dict[str, Any] = field(default_factory=dict)
    sampled: bool = True

    def add(self, stage: str, ms: Optional[float] = None, **data: Any) -> Dict[str, Any]:
        entry: Dict[str, Any] = {"stage": stage, "at_ms": round((time.perf_counter() - self.started) * 1000, 1)}
        if ms is not None:
            entry["ms"] = round(ms, 1)
        entry.update(data)
        self.stages.append(entry)
        return entry

    @contextmanager
    def timed(self, stage: str, **data: Any) -> Iterator[Dict[str, Any]]:
        """Records `stage` with its duration; the yielded dict can be filled with results."""
        t0 = time.perf_counter()
        entry = self.add(stage, **data)
        try:
            yield entry
        finally:
            entry["ms"] = round((time.perf_counter() - t0) * 1000, 1)

    def stage(self, name: str) -> Optional[Dict[str, Any]]:
        """The last record of stage `name`."""
        for entry in reversed(self.stages):
            if entry["stage"] == name:
                return entry
        return None

    def should_keep(self) -> bool:
        if self.sampled:
            return True
        if self.outcome.get("is_refusal") or self.outcome.get("error"):
            return True
        verification = self.stage("verification")
        return bool(verification and verification.get("dropped")) or any(
            s["stage"] in ALWAYS_KEEP_STAGES for s in self.stages
        )

    def to_record(self, redact: bool = True) -> Dict[str, Any]:
        """JSON-safe record; user-typed and generated text is PII-masked (passages are masked at ingestion)."""
        clean = PiiSanitizer.sanitize if redact else (lambda s: s)
        outcome = dict(self.outcome)
        if isinstance(outcome.get("answer"), str):
            outcome["answer"] = clean(outcome["answer"])
        stages = []
        for entry in self.stages:
            entry = dict(entry)
            for key in USER_TEXT_FIELDS:
                if isinstance(entry.get(key), str):
                    entry[key] = clean(entry[key])
            if entry.get("dropped"):
                entry["dropped"] = [
                    dict(d, sentence=clean(d.get("sentence", ""))) if isinstance(d, dict) else d
                    for d in entry["dropped"]
                ]
            stages.append(entry)
        return {
            "schema": TRACE_SCHEMA_VERSION,
            "trace_id": self.trace_id,
            "tenant_id": self.tenant_id,
            "session_id": self.session_id,
            "user_id": self.user_id,
            "endpoint": self.endpoint,
            "model": self.model,
            "query": clean(self.query),
            "created_at": self.created_at,
            "total_ms": round((time.perf_counter() - self.started) * 1000, 1),
            "stages": stages,
            "outcome": outcome,
            "config": self.config,
        }


_current: contextvars.ContextVar[Optional[TurnTrace]] = contextvars.ContextVar("rag_turn_trace", default=None)


def begin_turn(
    tenant_id: str,
    session_id: str,
    user_id: str,
    query: str,
    trace_id: Optional[str] = None,
    endpoint: str = "chat",
    model: str = "",
    sample_rate: float = 1.0,
    config: Optional[Dict[str, Any]] = None,
) -> TurnTrace:
    trace = TurnTrace(
        trace_id=trace_id or new_trace_id(), tenant_id=tenant_id, session_id=session_id, user_id=user_id,
        query=query, endpoint=endpoint, model=model, config=dict(config or {}),
        sampled=sample_rate >= 1.0 or random.random() < max(sample_rate, 0.0),
    )
    _current.set(trace)
    return trace


def current_turn() -> Optional[TurnTrace]:
    return _current.get()


def end_turn() -> None:
    _current.set(None)


def current_trace_id() -> str:
    t = _current.get()
    return t.trace_id if t else new_trace_id()


def trace_stage(stage: str, ms: Optional[float] = None, **data: Any) -> None:
    t = _current.get()
    if t is not None:
        t.add(stage, ms=ms, **data)


def dropped_sentences(dropped: Sequence[Any]) -> List[Dict[str, str]]:
    return [{"problem": str(p), "sentence": str(s)[:400]} for p, s in (dropped or [])]
