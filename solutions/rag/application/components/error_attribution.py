"""
5-Stage Error Attribution Matrix Component for AIP Enterprise RAG (Slide 140–145, EXEC-RAG-04, FR-EXEC-03).
Classifies root causes of RAG failures and user dislikes into 5 canonical stages:
1. PRE_RETRIEVAL_ERROR: Query rewrite drift, intent misclassification, or timeout.
2. RETRIEVAL_MISS: Dense + BM25 fusion failed to surface relevant chunks in Top-20.
3. RERANKER_DROP: Cross-Encoder scored relevant chunks poorly or aggressive cutoff pruned them.
4. LLM_SYNTHESIS_ERROR: Context was provided correctly, but LLM misread, hallucinated, or failed instructions.
5. OOD_HALLUCINATION: Out-of-domain query answered with ungrounded speculation instead of clean refusal.
"""

from __future__ import annotations

from enum import Enum
import logging
import time
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

logger = logging.getLogger("aip-rag.error_attribution")


class ErrorStage(str, Enum):
    PRE_RETRIEVAL_ERROR = "PRE_RETRIEVAL_ERROR"
    RETRIEVAL_MISS = "RETRIEVAL_MISS"
    RERANKER_DROP = "RERANKER_DROP"
    LLM_SYNTHESIS_ERROR = "LLM_SYNTHESIS_ERROR"
    OOD_HALLUCINATION = "OOD_HALLUCINATION"


class AttributionResult(BaseModel):
    stage: ErrorStage
    confidence: float = Field(ge=0.0, le=1.0)
    root_cause_explanation: str
    telemetry_snapshot: Dict[str, Any] = Field(default_factory=dict)
    timestamp: float = Field(default_factory=time.time)


class ErrorAttributionService:
    """Production 5-Stage Error Attribution Engine (EXEC-RAG-04)."""

    @staticmethod
    def attribute(
        query: str,
        answer: str,
        rating: Any,
        user_feedback: Optional[str] = None,
        error_category: Optional[str] = None,
        telemetry: Optional[Dict[str, Any]] = None,
        citations: Optional[List[Dict[str, Any]]] = None,
        pre_retrieval_tier: Optional[str] = None,
        intent: Optional[str] = None,
        rerank_top1_score: Optional[float] = None,
        circuit_breaker_triggered: bool = False,
    ) -> AttributionResult:
        """
        Diagnoses trace telemetry and feedback to assign the definitive failure stage.
        """
        telemetry = telemetry or {}
        citations = citations or []
        feedback_text = (user_feedback or "").lower()
        err_cat = (error_category or "").lower()

        # Extract telemetry metrics
        top1 = rerank_top1_score if rerank_top1_score is not None else telemetry.get("rerank_top1_score", 0.0)
        tier = pre_retrieval_tier or telemetry.get("pre_retrieval_tier", "")
        cit_count = len(citations)

        # 1. Check for OOD Hallucination
        # If no citations were grounded or score was below 0.75, but LLM still gave a speculative response
        is_refusal = (
            "không có trong tài liệu" in answer.lower()
            or "vui lòng liên hệ bộ phận liên quan" in answer.lower()
            or circuit_breaker_triggered
        )
        if not is_refusal and (top1 < 0.75 or cit_count == 0):
            if "bịa" in feedback_text or "ảo giác" in feedback_text or "hallucination" in err_cat or cit_count == 0:
                return AttributionResult(
                    stage=ErrorStage.OOD_HALLUCINATION,
                    confidence=0.92,
                    root_cause_explanation=(
                        f"Mô hình sinh câu trả lời suy đoán ngoài phạm vi (OOD) mà không có căn cứ tài liệu hợp lệ "
                        f"(Rerank Top-1={top1:.2f} < 0.75, Số trích dẫn={cit_count})."
                    ),
                    telemetry_snapshot={"rerank_top1_score": top1, "citations": cit_count, "tier": tier},
                )

        # 2. Check for Pre-Retrieval Errors
        # If pre-retrieval timed out, errored, or Intent was misrouted
        if "timeout" in tier.lower() or "error" in tier.lower():
            return AttributionResult(
                stage=ErrorStage.PRE_RETRIEVAL_ERROR,
                confidence=0.95,
                root_cause_explanation=(
                    f"Tầng Pre-Retrieval gặp sự cố ({tier}): LLM tiền xử lý câu hỏi vượt quá hạn định "
                    f"hoặc ngắt kết nối trước khi truy xuất."
                ),
                telemetry_snapshot={"tier": tier, "query": query},
            )

        if intent == "CHITCHAT" and any(k in query.lower() for k in ["hướng dẫn", "quy định", "làm thế nào", "sự cố", "lỗi"]):
            return AttributionResult(
                stage=ErrorStage.PRE_RETRIEVAL_ERROR,
                confidence=0.88,
                root_cause_explanation="Bộ phân loại ý định (Intent Classifier) định tuyến nhầm câu hỏi nghiệp vụ sang luồng CHITCHAT.",
                telemetry_snapshot={"intent": intent, "query": query},
            )

        # 3. Check for Retrieval Miss
        # If raw retrieval returned empty or very low initial similarity
        retrieval_count = telemetry.get("raw_retrieval_count", 20)
        if retrieval_count == 0 or "không tìm thấy" in feedback_text:
            return AttributionResult(
                stage=ErrorStage.RETRIEVAL_MISS,
                confidence=0.85,
                root_cause_explanation="Tầng truy xuất Hybrid (Dense + BM25) không tìm thấy chunk văn bản phù hợp trong kho tri thức.",
                telemetry_snapshot={"retrieval_count": retrieval_count},
            )

        # 4. Check for Reranker Drop
        # If retrieval had candidates, but reranker rejected them via circuit breaker or steep cliff
        if circuit_breaker_triggered or top1 < 0.75:
            return AttributionResult(
                stage=ErrorStage.RERANKER_DROP,
                confidence=0.82,
                root_cause_explanation=(
                    f"Mô hình Cross-Encoder Reranker ngắt mạch (Circuit Breaker) do điểm số cao nhất "
                    f"({top1:.4f}) không đạt ngưỡng an toàn 0.75."
                ),
                telemetry_snapshot={"rerank_top1_score": top1, "circuit_breaker": circuit_breaker_triggered},
            )

        # 5. Check for LLM Synthesis Error
        # When context was provided with high confidence, but LLM made mistakes in synthesis
        return AttributionResult(
            stage=ErrorStage.LLM_SYNTHESIS_ERROR,
            confidence=0.80,
            root_cause_explanation=(
                f"Tài liệu tham khảo đạt độ tin cậy cao (Top-1={top1:.2f}, {cit_count} trích dẫn), "
                f"nhưng mô hình LLM tổng hợp thông tin chưa chính xác theo ngữ cảnh."
            ),
            telemetry_snapshot={"rerank_top1_score": top1, "citations": cit_count},
        )

    @classmethod
    def generate_executive_dashboard(cls, records: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Computes the Executive Error Attribution Breakdown & Funnel Analysis (EXEC-RAG-04 DoD).
        """
        total = len(records)
        if total == 0:
            return {
                "total_feedbacks": 0,
                "breakdown": {s.value: {"count": 0, "percentage": 0.0} for s in ErrorStage},
                "primary_bottleneck": "NONE",
            }

        counts: Dict[str, int] = {s.value: 0 for s in ErrorStage}
        for r in records:
            stage = r.get("attributed_stage") or r.get("stage")
            if stage in counts:
                counts[stage] += 1
            else:
                counts[ErrorStage.LLM_SYNTHESIS_ERROR.value] += 1

        breakdown = {
            s: {
                "count": count,
                "percentage": round((count / total) * 100, 2),
            }
            for s, count in counts.items()
        }

        # Find primary bottleneck
        primary_stage = max(counts.items(), key=lambda x: x[1])[0]

        return {
            "total_feedbacks": total,
            "breakdown": breakdown,
            "primary_bottleneck": primary_stage,
        }


error_attribution_service = ErrorAttributionService()
