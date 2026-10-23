"""
Generation Metrics Evaluator (Answer Correctness, Completeness, Abstention).
Strict separation:
- Out-of-Domain (unanswerable) cases ONLY evaluate abstention_quality.
- In-Domain (answerable) cases evaluate answer_correctness and completeness.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional


def _tokenize(text: str) -> List[str]:
    clean = re.sub(r"[^\w\s]", " ", text.lower())
    return [w for w in clean.split() if len(w) > 1]


def compute_token_f1(pred: str, target: str) -> float:
    pred_tokens = set(_tokenize(pred))
    target_tokens = set(_tokenize(target))
    if not pred_tokens or not target_tokens:
        return 0.0
    overlap = pred_tokens.intersection(target_tokens)
    if not overlap:
        return 0.0
    precision = len(overlap) / len(pred_tokens)
    recall = len(overlap) / len(target_tokens)
    return 2 * (precision * recall) / (precision + recall)


def evaluate_generation(
    generated_answer: str,
    expected_answer: str,
    required_facts: List[str],
    answerable: bool = True,
) -> Dict[str, Optional[float]]:
    """
    Computes generation scores:
    - If answerable is False (OOD):
        answer_correctness = None (N/A)
        completeness = None (N/A)
        abstention_quality = 1.0 if refused, 0.0 if hallucinated
    - If answerable is True:
        answer_correctness = Token F1 score
        completeness = required_facts coverage
        abstention_quality = None (or 0.0 if erroneously refused)
    """
    ans_lower = generated_answer.lower().strip()
    refusal_keywords = [
        "không có trong tài liệu",
        "không nằm trong tài liệu",
        "không tìm thấy thông tin",
        "thông tin về vấn đề này không có",
        "tôi không tìm thấy",
        "không được đề cập",
        "vui lòng liên hệ bộ phận liên quan",
    ]

    is_refusal = any(kw in ans_lower for kw in refusal_keywords)

    # 1. Out-of-Domain / Unanswerable cases
    if not answerable:
        return {
            "answer_correctness": None,
            "completeness": None,
            "abstention_quality": 1.0 if is_refusal else 0.0,
        }

    # 2. In-Domain / Answerable cases
    if is_refusal:
        # Erroneously refused an answerable question
        return {
            "answer_correctness": 0.0,
            "completeness": 0.0,
            "abstention_quality": None,
        }

    # Answer correctness via Token F1
    f1 = compute_token_f1(generated_answer, expected_answer)

    # Completeness via required_facts coverage
    if required_facts:
        found_facts = 0
        for fact in required_facts:
            fact_tokens = set(_tokenize(fact))
            ans_tokens = set(_tokenize(generated_answer))
            if len(fact_tokens.intersection(ans_tokens)) >= max(1, len(fact_tokens) * 0.6):
                found_facts += 1
        completeness = found_facts / len(required_facts)
    else:
        completeness = f1

    return {
        "answer_correctness": round(f1, 4),
        "completeness": round(completeness, 4),
        "abstention_quality": None,
    }
