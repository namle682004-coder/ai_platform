"""
The benchmark grades with the RAG service's own definitions (identifier syntax, verification
helpers, trace diagnosis), so "a code is present" or "the gate refused" means the same thing in
evaluation and at runtime.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
for p in (REPO_ROOT, REPO_ROOT / "packages" / "common"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from solutions.rag.application.components.answer_verifier import is_english_text, split_sentences  # noqa: E402
from solutions.rag.application.components.conversation_policy import TICKET_RE  # noqa: E402
from solutions.rag.application.components.lexical_evidence import extract_identifiers, normalize_for_match  # noqa: E402
from solutions.rag.application.components.prompt_builder import REFUSAL_MESSAGE  # noqa: E402
from solutions.rag.application.components.trace_diagnosis import (  # noqa: E402
    STAGE_ORDER,
    Diagnosis,
    context_refs,
    diagnose,
    final_route,
    needle_in_refs,
    needle_in_text,
    rerank_keep,
    reranked_refs,
    retrieval_refs,
)

__all__ = [
    "REPO_ROOT", "REFUSAL_MESSAGE", "STAGE_ORDER", "TICKET_RE", "Diagnosis", "context_refs", "diagnose",
    "extract_identifiers", "final_route", "is_english_text", "needle_in_refs", "needle_in_text",
    "normalize_for_match", "rerank_keep", "reranked_refs", "retrieval_refs", "split_sentences",
]
