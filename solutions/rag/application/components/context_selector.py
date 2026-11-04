"""
Adaptive context selection between reranking and prompt assembly.

- Adaptive top-k: instead of a fixed k, every passage whose blended relevance (cross-encoder score
  and IDF-weighted keyword coverage) is within a relative margin of the best passage is kept, up to
  a character budget. A specific question keeps one or two dominant passages; an overview question,
  where many passages of the same section match equally, keeps the whole section. Passages are then
  presented in document order so answers follow the document's own structure.
- Document card: the verbatim opening lines and heading outline of each contributing document, so
  questions about the document itself (title, number, date, issuer, structure) are answerable even
  when retrieval did not rank the header chunk.

Everything is computed from the retrieved passages; no vocabulary is built in.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .lexical_evidence import candidate_text

_BREADCRUMB_PREFIX_RE = re.compile(r"^\[(?:Ngữ cảnh|Tài liệu)[^\]]*\]\s*", re.MULTILINE)


def payload_of(c: Any) -> Dict[str, Any]:
    if isinstance(c, dict):
        return c.get("payload") or c
    return getattr(c, "metadata", {}) or {}


def chunk_order_key(c: Any) -> Tuple[str, int]:
    p = payload_of(c)
    try:
        idx = int(p.get("chunk_index", 0) or 0)
    except (TypeError, ValueError):
        idx = 0
    return str(p.get("doc_id") or ""), idx


def candidate_key(c: Any) -> str:
    if isinstance(c, dict) and c.get("id") is not None:
        return str(c.get("id"))
    p = payload_of(c)
    return f"{p.get('doc_id')}_{p.get('chunk_index')}"


@dataclass
class ContextSelection:
    chunks: List[Any]
    scores: Dict[str, float] = field(default_factory=dict)


def select_adaptive_context(
    pool: Sequence[Any],
    scores: Dict[str, float],
    relative_cutoff: float = 0.6,
    char_budget: int = 9000,
    min_k: int = 4,
    max_k: int = 12,
) -> ContextSelection:
    """
    Keeps every passage scoring >= relative_cutoff * best (plus the top `min_k`), strongest first
    until `char_budget` / `max_k` is reached, then restores document order.
    """
    if not pool:
        return ContextSelection(chunks=[])
    ranked = sorted(pool, key=lambda c: scores.get(candidate_key(c), 0.0), reverse=True)
    best = scores.get(candidate_key(ranked[0]), 0.0)
    floor = relative_cutoff * best
    chosen: List[Any] = []
    used = 0
    for i, c in enumerate(ranked):
        s = scores.get(candidate_key(c), 0.0)
        if i >= min_k and s < floor:
            break
        size = len(candidate_text(c))
        if chosen and (used + size > char_budget or len(chosen) >= max_k):
            continue
        chosen.append(c)
        used += size
    # Documents in lost-in-the-middle order (best first, second best last); inside a document,
    # passages keep their original order so the answer follows the document structure.
    groups: Dict[str, List[Any]] = {}
    for c in ranked:
        if c in chosen:
            groups.setdefault(chunk_order_key(c)[0], []).append(c)
    doc_ids = list(groups)
    u_shaped = doc_ids[0::2] + doc_ids[1::2][::-1] if len(doc_ids) > 2 else doc_ids
    ordered = [c for d in u_shaped for c in sorted(groups[d], key=chunk_order_key)]
    return ContextSelection(chunks=ordered, scores={candidate_key(c): scores.get(candidate_key(c), 0.0) for c in ordered})


@dataclass
class DocumentCard:
    doc_id: str
    title: str
    header_lines: List[str] = field(default_factory=list)
    outline: List[str] = field(default_factory=list)

    def to_context_text(self) -> str:
        lines = [
            "THÔNG TIN VĂN BẢN (trích nguyên văn phần đầu và cấu trúc của tài liệu):",
            f"- Tên tài liệu: {self.title}",
        ]
        if self.header_lines:
            lines.append("- Các dòng đầu văn bản: " + " | ".join(self.header_lines))
        if self.outline:
            lines.append("- Các phần chính theo thứ tự trong văn bản: " + "; ".join(self.outline))
        return "\n".join(lines)


def build_document_card(doc_chunks: Sequence[Any], fallback_title: str = "", max_header_lines: int = 4) -> Optional[DocumentCard]:
    """Verbatim opening lines and top-level heading outline of a document (no interpretation)."""
    if not doc_chunks:
        return None
    ordered = sorted(doc_chunks, key=chunk_order_key)
    p0 = payload_of(ordered[0])
    title = str(p0.get("title") or fallback_title or "").strip()
    head_text = _BREADCRUMB_PREFIX_RE.sub("", candidate_text(ordered[0]))
    header_lines: List[str] = []
    for line in head_text.splitlines():
        s_line = line.strip()
        if not s_line or s_line.startswith("|"):
            continue
        if title and s_line.upper() == title.upper():
            continue
        header_lines.append(s_line[:240])
        if len(header_lines) >= max_header_lines:
            break
    return DocumentCard(
        doc_id=str(p0.get("doc_id") or ""),
        title=title,
        header_lines=header_lines,
        outline=outline_from_candidates(ordered, limit=20),
    )


def document_card_candidate(card: DocumentCard) -> Dict[str, Any]:
    """Wraps a DocumentCard as a candidate so it flows through prompt assembly and citations."""
    return {
        "id": f"doccard_{card.doc_id}",
        "score": 1.0,
        "payload": {
            "doc_id": card.doc_id,
            "title": card.title,
            "page_number": 1,
            "chunk_index": -1,
            "heading": "Thông tin văn bản",
            "heading_path": "Thông tin văn bản",
            "text": card.to_context_text(),
        },
    }


def outline_from_candidates(candidates: Sequence[Any], limit: int = 8) -> List[str]:
    """Top-level section names of the given passages, in document order."""
    seen: List[str] = []
    for c in sorted(candidates, key=chunk_order_key):
        h = str(payload_of(c).get("heading_path") or "").split(" > ")[0].strip()
        if h and h != "Thông tin văn bản" and h not in seen:
            seen.append(h)
        if len(seen) >= limit:
            break
    return seen
