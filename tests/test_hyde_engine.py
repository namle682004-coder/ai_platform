"""
Unit and Integration Tests for HyDE Engine (Hypothetical Document Embeddings - Slide 138).
Validates:
1. Adaptive HyDE Triggering:
   - Short queries (< 8 words) trigger automatically
   - Definitional / conceptual queries trigger automatically
   - Long specific queries bypass HyDE to preserve latency
   - Explicit client flag overrides (enable_hyde=True / False)
2. Hypothetical Document Generation:
   - Zero-shot prompt generation produces domain passages
   - Speculative timeout guardrail prevents latency spikes
   - Exception handling prevents retrieval failure
3. Vector Fusion Engine:
   - Weighted vector interpolation (alpha=0.4)
   - L2 Unit Normalization (||v|| = 1.0)
   - Dimension mismatch safety
4. End-to-End RagChatUseCase Integration:
   - Non-streaming response carries hyde_active and hypothetical_doc
   - Streaming SSE done event carries hyde_active
5. Zero Vietnamese Legal Regex Audit:
   - Verifies 100% domain-agnostic implementation without hardcoded legal keywords.
"""

import asyncio
import inspect
import json
import math
import re
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple

from solutions.rag.application.components.hyde_generator import (
    HyDEGenerator,
    HyDEResult,
)
from solutions.rag.application.dtos import RagChatRequestDTO, RagChatResponseDTO
from solutions.rag.application.use_cases.chat_use_case import RagChatUseCase


class MockHyDELLM:
    """Mock LLM simulating hypothetical document generation."""

    def __init__(self, canned_response: str = "Tài liệu quy định chi tiết về thời gian làm việc và chế độ nghỉ phép năm của nhân viên.", delay: float = 0.0):
        self.canned_response = canned_response
        self.delay = delay
        self.call_count = 0
        self.calls: List[List[Dict[str, str]]] = []

    async def generate(
        self,
        messages: List[Dict[str, str]],
        model: str = "chat-general-standard",
        temperature: float = 0.3,
        max_tokens: int = 96,
        authorization: Optional[str] = None,
    ) -> Tuple[str, int, int]:
        self.call_count += 1
        self.calls.append(messages)
        if self.delay > 0:
            await asyncio.sleep(self.delay)
        return self.canned_response, 30, 20

    async def stream_generate(
        self,
        messages: List[Dict[str, str]],
        model: str,
        temperature: float = 0.2,
        max_tokens: int = 1024,
        authorization: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        self.call_count += 1
        yield "Phản "
        yield "hồi "
        yield "HyDE [1]."


class MockTimeoutLLM:
    """Mock LLM simulating timeout."""

    async def generate(self, *args, **kwargs) -> Tuple[str, int, int]:
        await asyncio.sleep(0.5)
        return "Quá hạn", 10, 10


class MockFailingLLM:
    """Mock LLM simulating network failure."""

    async def generate(self, *args, **kwargs) -> Tuple[str, int, int]:
        raise RuntimeError("vLLM engine unavailable")


def test_hyde_adaptive_trigger_rules():
    """Validates selective triggering rules for HyDE according to Slide 138."""
    gen = HyDEGenerator()

    # 1. Short queries (< 8 words) -> Auto-activate
    active1, reason1 = gen.should_activate("SLA là gì?")
    assert active1 is True
    assert reason1 == "short_query"

    active2, reason2 = gen.should_activate("Chính sách làm việc từ xa WFH")
    assert active2 is True
    assert reason2 == "short_query"

    # 2. Definitional queries (contain 'khái niệm', 'định nghĩa', 'what is') -> Auto-activate
    active3, reason3 = gen.should_activate("Khái niệm về bảo mật dữ liệu cá nhân theo tiêu chuẩn quốc tế")
    assert active3 is True
    assert reason3 == "definitional_query"

    active4, reason4 = gen.should_activate("What is the zero trust architecture security policy")
    assert active4 is True
    assert reason4 == "definitional_query"

    # 3. Long factual queries (> 8 words without definitional cues) -> Bypass to conserve latency
    active5, reason5 = gen.should_activate("Nhân viên chính thức có được đăng ký làm việc vào ngày thứ bảy và chủ nhật không")
    assert active5 is False
    assert reason5 == "bypassed_long_query"

    # 4. Explicit client overrides
    active6, reason6 = gen.should_activate("Nhân viên chính thức có được đăng ký làm việc vào ngày thứ bảy và chủ nhật không", enable_hyde=True)
    assert active6 is True
    assert reason6 == "explicit_enable"

    active7, reason7 = gen.should_activate("SLA là gì?", enable_hyde=False)
    assert active7 is False
    assert reason7 == "bypassed_explicit"


def test_hyde_hypothetical_doc_generation():
    """Validates generation of hypothetical document when HyDE is triggered."""
    async def _run():
        gen = HyDEGenerator()
        mock_llm = MockHyDELLM(canned_response="Quy trình thanh toán công tác phí yêu cầu cung cấp hóa đơn VAT hợp lệ trong vòng 5 ngày làm việc.")

        # Test active generation for short query
        res: HyDEResult = await gen.generate_hypothetical_doc(
            query="Quy trình công tác phí?",
            llm_port=mock_llm,
        )

        assert res.is_active is True
        assert res.trigger_reason == "short_query"
        assert "công tác phí" in res.hypothetical_document
        assert res.latency_ms > 0.0
        assert mock_llm.call_count == 1

        # Test bypass for long query
        res_bypassed: HyDEResult = await gen.generate_hypothetical_doc(
            query="Hướng dẫn chi tiết về các bước đăng ký phê duyệt lịch công tác tại các tỉnh miền Trung",
            llm_port=mock_llm,
        )
        assert res_bypassed.is_active is False
        assert res_bypassed.trigger_reason == "bypassed_long_query"
        assert res_bypassed.hypothetical_document == ""

    asyncio.run(_run())


def test_hyde_timeout_and_error_guardrails():
    """Validates that HyDE timeout and errors gracefully fall back without breaking the retrieval pipeline."""
    async def _run():
        gen = HyDEGenerator()

        # 1. Timeout guardrail (timeout=0.05s while LLM takes 0.5s)
        slow_llm = MockTimeoutLLM()
        res_timeout = await gen.generate_hypothetical_doc(
            query="WFH là gì?",
            llm_port=slow_llm,
            timeout=0.05,
        )
        assert res_timeout.is_active is False
        assert res_timeout.trigger_reason == "llm_timeout_fallback"
        assert res_timeout.hypothetical_document == ""

        # 2. Exception guardrail
        failing_llm = MockFailingLLM()
        res_err = await gen.generate_hypothetical_doc(
            query="Quy chế thưởng?",
            llm_port=failing_llm,
        )
        assert res_err.is_active is False
        assert res_err.trigger_reason == "llm_error_fallback"
        assert res_err.hypothetical_document == ""

    asyncio.run(_run())


def test_hyde_vector_fusion_math():
    """Validates weighted interpolation and L2 unit normalization in vector fusion."""
    gen = HyDEGenerator()

    # Synthetic 4-dimensional unit vectors
    q_vec = [1.0, 0.0, 0.0, 0.0]
    h_vec = [0.0, 1.0, 0.0, 0.0]

    # Fusion with alpha=0.4: blended = [0.4, 0.6, 0.0, 0.0]
    fused = gen.fuse_embeddings(q_vec, h_vec, alpha=0.4)

    assert len(fused) == 4
    # Check L2 unit norm: ||fused|| = 1.0
    l2_norm = math.sqrt(sum(x * x for x in fused))
    assert math.isclose(l2_norm, 1.0, abs_tol=1e-5)

    # Relative magnitude: hypothetical document (0.6) has greater weight than query (0.4)
    assert fused[1] > fused[0]
    assert math.isclose(fused[0] / fused[1], 0.4 / 0.6, abs_tol=1e-5)

    # Dimension mismatch safety
    mismatched = gen.fuse_embeddings(q_vec, [0.5, 0.5])
    assert mismatched == q_vec


def test_rag_chat_use_case_with_hyde_integration():
    """Validates that RagChatUseCase executes with HyDE vector search and returns metadata."""
    async def _run():
        class MockEmbeddingService:
            def __init__(self):
                self.calls = []

            async def get_embedding(self, text: str) -> List[float]:
                self.calls.append(text)
                return [0.05] * 768

        class MockVectorStore:
            def __init__(self):
                self.last_search_vector = None

            async def search(self, **kwargs) -> List[Dict[str, Any]]:
                self.last_search_vector = kwargs.get("query_vector")
                return [
                    {
                        "doc_id": "doc_policy_01",
                        "score": 0.95,
                        "payload": {
                            "doc_id": "doc_policy_01",
                            "title": "Chính sách WFH 2026",
                            "page_number": 1,
                            "text": "Nhân viên được phép làm việc từ xa tối đa 2 ngày mỗi tuần.",
                        },
                    }
                ]

        class MockSessionRepo:
            async def get_session(self, *args, **kwargs): return None
            async def save_session(self, **kwargs): pass

        mock_llm = MockHyDELLM(canned_response="Chính sách quy định nhân viên chính thức được phép làm việc từ xa tối đa 2 ngày/tuần.")
        emb_service = MockEmbeddingService()
        vec_store = MockVectorStore()

        use_case = RagChatUseCase(
            vector_store=vec_store,
            embedding_service=emb_service,
            llm_service=mock_llm,
            session_repo=MockSessionRepo(),
        )

        # 1. Short query -> Auto-activates HyDE
        req_short = RagChatRequestDTO(
            query="Chính sách WFH",
            history=None,
        )
        resp: RagChatResponseDTO = await use_case.execute(req_short)

        assert resp.hyde_active is True
        assert resp.hypothetical_doc is not None
        assert "làm việc từ xa" in resp.hypothetical_doc
        assert resp.hyde_latency_ms >= 0.0
        # Check that both query and hypothetical doc were embedded
        assert len(emb_service.calls) >= 2

        # 2. Streaming execution with HyDE
        stream_gen = use_case.stream_execute(req_short)
        stream_events = []
        async for event in stream_gen:
            if event.startswith("data: "):
                payload = json.loads(event[6:].strip())
                stream_events.append(payload)

        done_event = next((e for e in stream_events if e.get("done") is True), None)
        assert done_event is not None
        assert done_event.get("hyde_active") is True
        assert done_event.get("hypothetical_doc") is not None

        # 3. Explicit disable (enable_hyde=False) -> Bypasses HyDE
        emb_service.calls.clear()
        req_disabled = RagChatRequestDTO(
            query="Chính sách WFH",
            enable_hyde=False,
            history=None,
        )
        resp_disabled = await use_case.execute(req_disabled)
        assert resp_disabled.hyde_active is False
        assert resp_disabled.hypothetical_doc is None

    asyncio.run(_run())


def test_zero_vietnamese_legal_regex_audit_in_hyde():
    """Strict architectural audit: ZERO hardcoded Vietnamese legal keywords in HyDE component."""
    source_code = inspect.getsource(HyDEGenerator)

    forbidden_patterns = [
        r"Chương\s+",
        r"Điều\s+",
        r"Khoản\s+",
        r"Mục\s+",
        r"VIETNAMESE_HEADING",
    ]

    for pattern in forbidden_patterns:
        found = re.findall(pattern, source_code)
        assert len(found) == 0, (
            f"VIOLATION: Found forbidden legal pattern '{pattern}' in HyDEGenerator! "
            f"Must maintain 100% domain-agnostic HyDE engine."
        )
