"""
Citation Precision and Grounded Attribution Evaluator.
Returns None for Out-Of-Domain / unanswerable cases.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set


def _normalize_title(val: Any) -> str:
    if not val:
        return ""
    s = str(val).lower().strip()
    for ext in (".docx", ".pdf", ".txt", ".xlsx"):
        if s.endswith(ext):
            s = s[:-len(ext)]
    return s


def evaluate_citations(
    citations: List[Dict[str, Any]],
    evidence: List[Dict[str, Any]],
    answerable: bool = True,
) -> Dict[str, Optional[float]]:
    """
    Evaluates citation precision against gold evidence docs.
    - If answerable is False or evidence is empty: returns None (N/A).
    - If citations are present: measures proportion of citations that match gold evidence.
    """
    if not answerable or not evidence:
        return {"citation_precision": None}

    if not citations:
        # Expected citations based on evidence but none were provided
        return {"citation_precision": 0.0}

    gold_titles: Set[str] = {
        _normalize_title(e.get("document_id")) for e in evidence if e.get("document_id")
    }

    correct_citations = 0
    for c in citations:
        title = _normalize_title(c.get("title") or c.get("document_id"))
        if any(g and (g in title or title in g) for g in gold_titles):
            correct_citations += 1

    precision = correct_citations / len(citations) if citations else 0.0
    return {
        "citation_precision": round(min(1.0, precision), 4)
    }
