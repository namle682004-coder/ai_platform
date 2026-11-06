"""
Per-stage retrieval metrics from a turn trace and the case's gold evidence (identifiers / quotes).

Recall is the share of gold needles present at each stage, so a drop between two stages points at
the stage that lost evidence: index -> retrieval -> rerank top-k -> prompt context -> answer.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Sequence

from ..runtime_bridge import (
    context_refs,
    extract_identifiers,
    needle_in_refs,
    needle_in_text,
    rerank_keep,
    reranked_refs,
    retrieval_refs,
)


def indexed_needles(needles: Sequence[str], snapshot: Optional[Dict[str, Any]]) -> Optional[List[str]]:
    """Needles present in any indexed chunk; None when no index snapshot is available."""
    if not snapshot:
        return None
    chunks = [c for d in snapshot.get("documents") or [] for c in d.get("chunks") or []]
    return [n for n in needles if needle_in_refs(n, chunks)]


def _recall(needles: Sequence[str], present: Iterable[str]) -> float:
    present = set(present)
    return round(sum(1 for n in needles if n in present) / len(needles), 4) if needles else 0.0


def _measurable(needles: Sequence[str], refs: Sequence[Dict[str, Any]]) -> bool:
    """Text needles can only be found in stages whose trace keeps passage text (retrieval keeps identifiers only)."""
    if any(r.get("text") for r in refs):
        return True
    return all(extract_identifiers(n) == [n.strip().upper()] for n in needles)


def _stage_recall(needles: Sequence[str], refs: Sequence[Dict[str, Any]]) -> Optional[float]:
    if not _measurable(needles, refs):
        return None
    return _recall(needles, [n for n in needles if needle_in_refs(n, refs)])


def stage_metrics(
    trace: Optional[Dict[str, Any]], needles: Sequence[str], indexed: Optional[Sequence[str]] = None
) -> Optional[Dict[str, Any]]:
    if not needles or not trace:
        return None
    retrieved = retrieval_refs(trace)
    ranked = reranked_refs(trace)
    keep = rerank_keep(trace)
    ctx = context_refs(trace)
    answer = str((trace.get("outcome") or {}).get("answer") or "")

    rank = next((i for i, r in enumerate(ranked, start=1) if any(needle_in_refs(n, [r]) for n in needles)), None)
    gold_ctx = sum(1 for r in ctx if any(needle_in_refs(n, [r]) for n in needles))
    out = {
        "retrieval_recall": _stage_recall(needles, retrieved),
        "rerank_recall_at_k": _stage_recall(needles, ranked[:keep]),
        "rerank_k": keep,
        "rerank_mrr": round(1.0 / rank, 4) if rank else 0.0,
        "context_recall": _stage_recall(needles, ctx),
        "context_precision": round(gold_ctx / len(ctx), 4) if ctx else 0.0,
        "answer_recall": _recall(needles, [n for n in needles if needle_in_text(n, answer)]),
    }
    if indexed is not None:
        out["index_recall"] = _recall(needles, indexed)
    return out
