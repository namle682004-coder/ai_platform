"""
Unit tests for FR-EXEC-03 and EXEC-RAG-04:
5-Stage Error Attribution Matrix & Executive Dashboard Generation.
"""

from solutions.rag.application.components.error_attribution import (
    ErrorStage,
    error_attribution_service,
)


def test_attribute_ood_hallucination():
    """When query is OOD with low reranker score or no citations but model speculates, attribute to OOD_HALLUCINATION."""
    res = error_attribution_service.attribute(
        query="Trường Đại học này có khoa Vũ trụ học không?",
        answer="Có, trường đào tạo ngành Vũ trụ học từ năm 2020.",
        rating="dislike",
        user_feedback="Thông tin bịa đặt, trường không có khoa này",
        rerank_top1_score=0.45,
        citations=[],
    )
    assert res.stage == ErrorStage.OOD_HALLUCINATION
    assert res.confidence >= 0.85
    assert "OOD" in res.root_cause_explanation or "ngoài phạm vi" in res.root_cause_explanation


def test_attribute_pre_retrieval_error():
    """When pre-retrieval times out or fails, attribute to PRE_RETRIEVAL_ERROR."""
    res = error_attribution_service.attribute(
        query="Nó có hiệu lực khi nào?",
        answer="Không tìm thấy thông tin",
        rating="dislike",
        pre_retrieval_tier="TIER_2_TIMEOUT_FALLBACK",
        telemetry={"tier": "TIER_2_TIMEOUT_FALLBACK"},
    )
    assert res.stage == ErrorStage.PRE_RETRIEVAL_ERROR
    assert "Pre-Retrieval" in res.root_cause_explanation


def test_attribute_retrieval_miss():
    """When raw retrieval returns 0 candidates, attribute to RETRIEVAL_MISS."""
    res = error_attribution_service.attribute(
        query="Mã lỗi ERR_SAMPLE_999",
        answer="Thông tin về vấn đề này không có trong tài liệu nội bộ",
        rating="dislike",
        user_feedback="Tài liệu có nói về mã lỗi này nhưng hệ thống không tìm thấy",
        telemetry={"raw_retrieval_count": 0},
    )
    assert res.stage == ErrorStage.RETRIEVAL_MISS
    assert "truy xuất" in res.root_cause_explanation.lower()


def test_attribute_reranker_drop():
    """When circuit breaker triggers due to score < 0.75, attribute to RERANKER_DROP."""
    res = error_attribution_service.attribute(
        query="Quy định thanh toán công tác phí",
        answer="Thông tin về vấn đề này không có trong tài liệu nội bộ được cung cấp.",
        rating="dislike",
        rerank_top1_score=0.68,
        circuit_breaker_triggered=True,
    )
    assert res.stage == ErrorStage.RERANKER_DROP
    assert "Reranker" in res.root_cause_explanation


def test_attribute_llm_synthesis_error():
    """When context has high score and citations exist, but answer is wrong, attribute to LLM_SYNTHESIS_ERROR."""
    res = error_attribution_service.attribute(
        query="Thời gian thử việc tối đa là bao lâu?",
        answer="Thời gian thử việc tối đa là 12 tháng.",
        rating="dislike",
        user_feedback="Tài liệu ghi 60 ngày nhưng bot lại trả lời 12 tháng",
        rerank_top1_score=0.92,
        citations=[{"doc_id": "doc1", "title": "Luật Lao động", "score": 0.92}],
    )
    assert res.stage == ErrorStage.LLM_SYNTHESIS_ERROR
    assert "LLM" in res.root_cause_explanation


def test_generate_executive_dashboard():
    """Test aggregation of feedback records into executive dashboard."""
    records = [
        {"attributed_stage": ErrorStage.OOD_HALLUCINATION.value},
        {"attributed_stage": ErrorStage.OOD_HALLUCINATION.value},
        {"attributed_stage": ErrorStage.LLM_SYNTHESIS_ERROR.value},
        {"attributed_stage": ErrorStage.PRE_RETRIEVAL_ERROR.value},
        {"attributed_stage": ErrorStage.RERANKER_DROP.value},
    ]
    dashboard = error_attribution_service.generate_executive_dashboard(records)
    assert dashboard["total_feedbacks"] == 5
    assert dashboard["breakdown"][ErrorStage.OOD_HALLUCINATION.value]["count"] == 2
    assert dashboard["breakdown"][ErrorStage.OOD_HALLUCINATION.value]["percentage"] == 40.0
    assert dashboard["primary_bottleneck"] == ErrorStage.OOD_HALLUCINATION.value
