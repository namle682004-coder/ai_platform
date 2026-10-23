"""
Unit Tests for AIP Enterprise RAG Benchmark Framework (Audited Ranx Edition).
Verifies schemas, ranx retrieval metrics, generation evaluation, and citation precision.
"""

import os
import pytest
from benchmarks.rag.src.rag_benchmark.schemas.dataset import GoldenCase, EvidenceChunk, QuestionType
from benchmarks.rag.src.rag_benchmark.evaluators.retrieval import evaluate_retrieval
from benchmarks.rag.src.rag_benchmark.evaluators.generation import evaluate_generation, compute_token_f1
from benchmarks.rag.src.rag_benchmark.evaluators.citation import evaluate_citations
from benchmarks.rag.src.rag_benchmark.runner.orchestrator import load_dataset


def test_golden_case_validation():
    case = GoldenCase(
        case_id="test_001",
        question="Quy chế nghỉ phép là gì?",
        expected_answer="Theo quy định cần báo trước 3 ngày.",
        required_facts=["3 ngày"],
        evidence=[EvidenceChunk(document_id="hr_policy.docx", quote="báo trước 3 ngày")],
    )
    assert case.case_id == "test_001"
    assert case.is_approved() is True
    assert case.question_type == QuestionType.SINGLE_HOP


def test_evaluate_retrieval_perfect_hit():
    retrieved = [
        {"document_id": "hr_policy.docx", "chunk_id": "c1", "score": 0.95},
        {"document_id": "other.docx", "chunk_id": "c2", "score": 0.80},
    ]
    evidence = [{"document_id": "hr_policy.docx", "chunk_id": "c1"}]

    metrics = evaluate_retrieval("case_test_1", retrieved, evidence, answerable=True)
    assert metrics["recall_at_1"] == 1.0
    assert metrics["recall_at_3"] == 1.0
    assert metrics["mrr_at_5"] == 1.0
    assert metrics["hit_at_3"] == 1.0
    assert metrics["ndcg_at_10"] is not None


def test_evaluate_retrieval_miss():
    retrieved = [
        {"document_id": "noise1.docx", "score": 0.95},
        {"document_id": "noise2.docx", "score": 0.80},
    ]
    evidence = [{"document_id": "target_contract.docx"}]

    metrics = evaluate_retrieval("case_test_2", retrieved, evidence, answerable=True)
    assert metrics["recall_at_1"] == 0.0
    assert metrics["recall_at_3"] == 0.0
    assert metrics["mrr_at_5"] == 0.0
    assert metrics["hit_at_3"] == 0.0


def test_evaluate_retrieval_unanswerable_is_none():
    retrieved = [{"document_id": "any.docx", "score": 0.95}]
    metrics = evaluate_retrieval("case_ood_1", retrieved, [], answerable=False)
    assert metrics["recall_at_1"] is None
    assert metrics["mrr_at_5"] is None


def test_evaluate_generation_f1_and_facts():
    pred = "Kế hoạch thử việc kéo dài trong 8 tuần cho lập trình viên."
    gold = "Kế hoạch thử việc của lập trình viên kéo dài 8 tuần."
    facts = ["8 tuần", "lập trình viên"]

    res = evaluate_generation(pred, gold, facts, answerable=True)
    assert res["answer_correctness"] > 0.80
    assert res["completeness"] == 1.0
    assert res["abstention_quality"] is None


def test_evaluate_generation_unanswerable_refusal():
    pred = "Thông tin về vấn đề này không có trong tài liệu nội bộ được cung cấp. Vui lòng liên hệ bộ phận liên quan."
    gold = "Thông tin về vấn đề này không có trong tài liệu nội bộ."
    facts = ["không có trong tài liệu"]

    res = evaluate_generation(pred, gold, facts, answerable=False)
    assert res["abstention_quality"] == 1.0
    assert res["answer_correctness"] is None
    assert res["completeness"] is None


def test_evaluate_citations_filter():
    citations = [
        {"title": "tài liệu k iêu đề", "score": 0.98},
        {"title": "Bien_ban_hop_25-09.docx", "score": 0.91},
    ]
    evidence = [{"document_id": "tài liệu k iêu đề"}]

    res = evaluate_citations(citations, evidence, answerable=True)
    assert res["citation_precision"] == 0.5


def test_evaluate_citations_ood_is_none():
    citations = [{"title": "random.docx"}]
    res = evaluate_citations(citations, [], answerable=False)
    assert res["citation_precision"] is None


def test_load_enterprise_dataset():
    path = "/home/namle/AI-Projects/llm-apps/ai_platform/benchmarks/rag/datasets/enterprise/internal_golden_v1.jsonl"
    cases = load_dataset(path)
    assert len(cases) == 6
    assert any(not c.answerable for c in cases)
