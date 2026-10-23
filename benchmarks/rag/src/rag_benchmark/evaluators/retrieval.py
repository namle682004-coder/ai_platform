"""
Standard Retrieval Metrics Evaluator using ranx (TREC/BEIR industrial standard).
Computes nDCG@10, Recall@K, MRR@K, Precision@K.
Strictly returns None for Out-Of-Domain / unanswerable cases.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from ranx import Qrels, Run, evaluate


def _normalize_id(val: Any) -> str:
    if not val:
        return ""
    s = str(val).lower().strip()
    for ext in (".docx", ".pdf", ".txt", ".xlsx"):
        if s.endswith(ext):
            s = s[:-len(ext)]
    return s


def evaluate_retrieval(
    case_id: str,
    retrieved_chunks: List[Dict[str, Any]],
    evidence: List[Dict[str, Any]],
    answerable: bool = True,
) -> Dict[str, Optional[float]]:
    """
    Evaluates retrieval performance using ranx.
    - If answerable is False or evidence is empty (OOD case): returns None for all retrieval metrics.
    - If answerable is True: computes standard TREC/BEIR metrics via ranx.
    """
    if not answerable or not evidence:
        return {
            "ndcg_at_10": None,
            "recall_at_1": None,
            "recall_at_3": None,
            "recall_at_5": None,
            "mrr_at_5": None,
            "precision_at_3": None,
            "hit_at_3": None,
        }

    # Build Qrels mapping for ranx
    qrels_dict: Dict[str, Dict[str, int]] = {case_id: {}}
    for e in evidence:
        doc_id = _normalize_id(e.get("document_id"))
        chunk_id = _normalize_id(e.get("chunk_id"))
        gold_id = doc_id or chunk_id
        if gold_id:
            qrels_dict[case_id][gold_id] = 1

    if not qrels_dict[case_id]:
        return {
            "ndcg_at_10": None,
            "recall_at_1": None,
            "recall_at_3": None,
            "recall_at_5": None,
            "mrr_at_5": None,
            "precision_at_3": None,
            "hit_at_3": None,
        }

    gold_ids = set(qrels_dict[case_id].keys())
    # Build Run mapping for ranx (strictly 1 slot per retrieved chunk to preserve rank ordering)
    run_dict: Dict[str, Dict[str, float]] = {case_id: {}}
    for rank, chunk in enumerate(retrieved_chunks, start=1):
        doc_id = _normalize_id(chunk.get("document_id"))
        title = _normalize_id(chunk.get("title"))
        chunk_id = _normalize_id(chunk.get("chunk_id"))
        score = float(chunk.get("score") or (1.0 / rank))

        # Map to matching gold identifier if any candidate attribute matches gold
        chosen_id = None
        for identifier in (doc_id, title, chunk_id):
            if identifier and identifier in gold_ids:
                chosen_id = identifier
                break
        if not chosen_id:
            chosen_id = doc_id or title or chunk_id or f"chunk_{rank}"

        if chosen_id not in run_dict[case_id]:
            run_dict[case_id][chosen_id] = score

    if not run_dict[case_id]:
        return {
            "ndcg_at_10": 0.0,
            "recall_at_1": 0.0,
            "recall_at_3": 0.0,
            "recall_at_5": 0.0,
            "mrr_at_5": 0.0,
            "precision_at_3": 0.0,
            "hit_at_3": 0.0,
        }

    qrels = Qrels(qrels_dict)
    run = Run(run_dict)

    res = evaluate(
        qrels,
        run,
        metrics=["ndcg@10", "recall@1", "recall@3", "recall@5", "mrr@5", "precision@3", "hit_rate@3"],
    )

    return {
        "ndcg_at_10": round(float(res.get("ndcg@10", 0.0)), 4),
        "recall_at_1": round(float(res.get("recall@1", 0.0)), 4),
        "recall_at_3": round(float(res.get("recall@3", 0.0)), 4),
        "recall_at_5": round(float(res.get("recall@5", 0.0)), 4),
        "mrr_at_5": round(float(res.get("mrr@5", 0.0)), 4),
        "precision_at_3": round(float(res.get("precision@3", 0.0)), 4),
        "hit_at_3": round(float(res.get("hit_rate@3", 0.0)), 4),
    }
