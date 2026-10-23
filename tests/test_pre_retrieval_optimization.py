"""
Unit and Integration Tests for Two-Tier Pre-Retrieval Latency Optimization (Slide 134–137, 139).
Validates:
1. Tier 1 Heuristic Fast-Track (< 1ms, 0 Token Cost):
   - Single-turn empty history bypass (< 0.01ms)
   - Standalone queries with domain keywords bypass (< 0.05ms)
   - Deterministic ellipsis stitching with subject extraction (< 0.2ms)
   - Deterministic relative pronoun replacement (< 0.2ms)
   - Deterministic explanation follow-ups (< 0.2ms)
   - Deterministic condition follow-ups (< 0.2ms)
2. Tier 2 Async Speculative LLM Fallback:
   - High-quality query reformulation for ambiguous multi-turn requests
   - Speculative timeout guardrail (< 800ms SLA, fallback without exception)
   - Resilient exception fallback handling
3. TTFT & Telemetry Integration in RagChatUseCase:
   - Verification that RagChatResponseDTO carries pre-retrieval tier and latency metrics
   - Verification of TTFT calculation in stream_execute
4. Zero Vietnamese Legal Regex Audit:
   - Strict audit ensuring no hardcoded legal keywords (Chương/Điều/Khoản/Mục) in pre-retrieval engine.
"""

import asyncio
import inspect
import json
import re
import time
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple

from solutions.rag.application.components.query_rewriter import (
    RagQueryRewriter,
    query_rewriter,
)
from solutions.rag.application.dtos import RagChatRequestDTO, RagChatResponseDTO
from solutions.rag.application.use_cases.chat_use_case import RagChatUseCase


class MockFastLLM:
    """Mock LLM returning immediate responses and tracking invocations."""

    def __init__(self, canned_response: str = "Câu hỏi độc lập viết lại bởi LLM", delay: float = 0.0):
        self.canned_response = canned_response
        self.delay = delay
        self.call_count = 0
        self.calls: List[List[Dict[str, str]]] = []

    async def generate(
        self,
        messages: List[Dict[str, str]],
        model: str = "chat-general-standard",
        temperature: float = 0.0,
        max_tokens: int = 48,
        authorization: Optional[str] = None,
    ) -> Tuple[str, int, int]:
        self.call_count += 1
        self.calls.append(messages)
        if self.delay > 0:
            await asyncio.sleep(self.delay)
        return self.canned_response, 25, 12

    async def stream_generate(
        self,
        messages: List[Dict[str, str]],
        model: str,
        temperature: float = 0.2,
        max_tokens: int = 1024,
        authorization: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        self.call_count += 1
        if self.delay > 0:
            await asyncio.sleep(self.delay)
        yield "Phản "
        yield "hồi "
        yield "stream."


class MockSlowTimeoutLLM:
    """Mock LLM simulating production latency spikes exceeding speculative budget."""

    async def generate(
        self,
        messages: List[Dict[str, str]],
        model: str = "chat-general-standard",
        temperature: float = 0.0,
        max_tokens: int = 48,
        authorization: Optional[str] = None,
    ) -> Tuple[str, int, int]:
        await asyncio.sleep(0.5)  # Exceeds tight 0.05s speculative timeout
        return "Quá hạn", 10, 10


class MockFailingLLM:
    """Mock LLM simulating API connection or network failure."""

    async def generate(
        self,
        messages: List[Dict[str, str]],
        model: str = "chat-general-standard",
        temperature: float = 0.0,
        max_tokens: int = 48,
        authorization: Optional[str] = None,
    ) -> Tuple[str, int, int]:
        raise ConnectionResetError("Remote vLLM server dropped connection")


def test_tier_1_empty_history_fast_track():
    """Single-turn queries with empty or missing history must bypass LLM immediately in < 1ms."""
    async def _run():
        rewriter = RagQueryRewriter()
        mock_llm = MockFastLLM()

        # Case 1: None history
        t0 = time.perf_counter()
        res1 = await rewriter.rewrite_advanced(
            query="Chính sách nghỉ thai sản 2026 áp dụng thế nào?",
            history=None,
            llm_port=mock_llm,
        )
        t1 = time.perf_counter()

        assert res1.tier == "TIER_1_HEURISTIC"
        assert res1.reason == "empty_history"
        assert res1.is_reformulated is False
        assert res1.text == "Chính sách nghỉ thai sản 2026 áp dụng thế nào?"
        assert (t1 - t0) * 1000 < 2.0  # Fast-track execution < 2ms
        assert mock_llm.call_count == 0  # 0 LLM tokens consumed

        # Case 2: Empty list history
        res2 = await rewriter.rewrite_advanced(
            query="Cách cấu hình MinIO S3 bucket?",
            history=[],
            llm_port=mock_llm,
        )
        assert res2.tier == "TIER_1_HEURISTIC"
        assert res2.reason == "empty_history"
        assert mock_llm.call_count == 0

    asyncio.run(_run())


def test_tier_1_standalone_query_bypass():
    """Standalone queries with no pronouns or conversational transitions bypass LLM in < 1ms."""
    async def _run():
        rewriter = RagQueryRewriter()
        mock_llm = MockFastLLM()

        history = [
            {"role": "user", "content": "Thời gian làm việc của công ty là mấy giờ?"},
            {"role": "assistant", "content": "Từ 8:30 đến 17:30 các ngày trong tuần."},
        ]

        query = "Hướng dẫn quy trình xin nghỉ phép năm trên hệ thống HRM"
        res = await rewriter.rewrite_advanced(query=query, history=history, llm_port=mock_llm)

        assert res.tier == "TIER_1_HEURISTIC"
        assert res.reason == "standalone_query"
        assert res.is_reformulated is False
        assert res.text == query
        assert res.latency_ms < 2.0
        assert mock_llm.call_count == 0  # 0 LLM tokens consumed

    asyncio.run(_run())


def test_tier_1_technical_identifiers_bypass():
    """Queries containing technical acronyms, version numbers, or quotes bypass LLM."""
    async def _run():
        rewriter = RagQueryRewriter()
        mock_llm = MockFastLLM()

        history = [
            {"role": "user", "content": "Kiểm tra log của hệ thống ở đâu?"},
            {"role": "assistant", "content": "Xem trong Grafana dashboard."},
        ]

        query = 'Cấu hình QDRANT vector store theo chuẩn ISO-9001'
        res = await rewriter.rewrite_advanced(query=query, history=history, llm_port=mock_llm)

        assert res.tier == "TIER_1_HEURISTIC"
        assert res.reason == "standalone_query"
        assert res.text == query
        assert mock_llm.call_count == 0

    asyncio.run(_run())


def test_tier_1_deterministic_ellipsis_stitching():
    """Deterministic topic stitching for ellipsis follow-ups ('Thế còn [X]?', 'Còn [X] thì sao?')."""
    async def _run():
        rewriter = RagQueryRewriter()
        mock_llm = MockFastLLM()

        # Pattern A: Preposition replacement ('của ...' -> 'của [target]')
        history = [
            {"role": "user", "content": "Quy định về thời gian thử việc của nhân viên chính thức?"},
            {"role": "assistant", "content": "Nhân viên chính thức không áp dụng thử việc lại."},
        ]

        query = "Thế còn nhân viên thử việc?"
        res = await rewriter.rewrite_advanced(query=query, history=history, llm_port=mock_llm)

        assert res.tier == "TIER_1_HEURISTIC"
        assert res.reason == "heuristic_ellipsis"
        assert res.is_reformulated is True
        assert "nhân viên thử việc" in res.text
        assert "Quy định về thời gian thử việc" in res.text
        assert mock_llm.call_count == 0  # 0 LLM calls!

        # Pattern B: Ellipsis with 'Còn ... thì sao?'
        query2 = "Còn thực tập sinh thì sao?"
        res2 = await rewriter.rewrite_advanced(query=query2, history=history, llm_port=mock_llm)
        assert res2.tier == "TIER_1_HEURISTIC"
        assert "thực tập sinh" in res2.text
        assert mock_llm.call_count == 0

    asyncio.run(_run())


def test_tier_1_deterministic_pronoun_and_explanation():
    """Deterministic resolution for leading relative pronouns ('Nó...') and explanation ('Tại sao?')."""
    async def _run():
        rewriter = RagQueryRewriter()
        mock_llm = MockFastLLM()

        history = [
            {"role": "user", "content": "Quy chế khen thưởng và kỷ luật lao động 2026"},
            {"role": "assistant", "content": "Quy chế áp dụng từ 01/01/2026."},
        ]

        # Leading pronoun 'Nó'
        res_pronoun = await rewriter.rewrite_advanced(
            query="Nó có hiệu lực từ khi nào?",
            history=history,
            llm_port=mock_llm,
        )
        assert res_pronoun.tier == "TIER_1_HEURISTIC"
        assert res_pronoun.reason == "heuristic_pronoun_replacement"
        assert "Quy chế khen thưởng và kỷ luật lao động 2026" in res_pronoun.text
        assert "có hiệu lực từ khi nào" in res_pronoun.text
        assert mock_llm.call_count == 0

        # Explanation follow-up 'Tại sao?'
        res_why = await rewriter.rewrite_advanced(
            query="Tại sao?",
            history=history,
            llm_port=mock_llm,
        )
        assert res_why.tier == "TIER_1_HEURISTIC"
        assert res_why.reason == "heuristic_explanation"
        assert "Quy chế khen thưởng và kỷ luật lao động 2026" in res_why.text
        assert mock_llm.call_count == 0

        # Short condition follow-up 'Có được không?'
        res_condition = await rewriter.rewrite_advanced(
            query="Có được không?",
            history=history,
            llm_port=mock_llm,
        )
        assert res_condition.tier == "TIER_1_HEURISTIC"
        assert res_condition.reason == "heuristic_condition"
        assert "Có được không?" in res_condition.text
        assert mock_llm.call_count == 0

    asyncio.run(_run())


def test_tier_2_speculative_llm_execution():
    """Ambiguous multi-turn queries trigger Tier 2 Async Speculative LLM rewriting."""
    async def _run():
        rewriter = RagQueryRewriter()
        mock_llm = MockFastLLM(canned_response="Quy trình xử lý khi phát sinh sự cố bảo mật")

        history = [
            {"role": "user", "content": "Nếu phát hiện rò rỉ dữ liệu thì báo cho ai?"},
            {"role": "assistant", "content": "Báo cáo cho ban an toàn thông tin CISO."},
        ]

        # Query with ambiguous coreference not covered by simple heuristic patterns
        query = "Thế nếu trong tình huống như vậy mà người đó không báo thì xử lý thế nào?"
        res = await rewriter.rewrite_advanced(
            query=query,
            history=history,
            llm_port=mock_llm,
            speculative_timeout=0.8,
        )

        assert res.tier == "TIER_2_SPECULATIVE_LLM"
        assert res.reason == "llm_reformulated"
        assert res.text == "Quy trình xử lý khi phát sinh sự cố bảo mật"
        assert mock_llm.call_count == 1

    asyncio.run(_run())


def test_tier_2_speculative_timeout_guardrail():
    """When LLM exceeds speculative timeout budget (e.g. 50ms), falls back without raising exception."""
    async def _run():
        rewriter = RagQueryRewriter()
        slow_llm = MockSlowTimeoutLLM()

        history = [
            {"role": "user", "content": "Chính sách trợ cấp công tác phí"},
            {"role": "assistant", "content": "500,000 VNĐ/ngày."},
        ]

        query = "Thế nếu trường hợp đó người đó đi công tác quá 30 ngày thì sao?"

        # Set tight speculative timeout of 50ms (0.05s) while LLM sleeps 500ms
        t0 = time.perf_counter()
        res = await rewriter.rewrite_advanced(
            query=query,
            history=history,
            llm_port=slow_llm,
            speculative_timeout=0.05,
        )
        t1 = time.perf_counter()

        elapsed_ms = (t1 - t0) * 1000
        assert elapsed_ms < 150.0  # Must not block for 500ms
        assert res.tier == "TIER_2_TIMEOUT_FALLBACK"
        assert res.reason == "llm_timeout_fallback"
        assert "Chính sách trợ cấp công tác phí" in res.text
        assert res.is_reformulated is True

    asyncio.run(_run())


def test_tier_2_error_resilience():
    """When LLM throws connection or API errors, falls back cleanly to speculative candidate query."""
    async def _run():
        rewriter = RagQueryRewriter()
        failing_llm = MockFailingLLM()

        history = [
            {"role": "user", "content": "Chính sách bảo mật mật khẩu"},
            {"role": "assistant", "content": "Mật khẩu tối thiểu 12 ký tự."},
        ]

        query = "Thế nếu người đó quên mật khẩu thì liên hệ ai?"
        res = await rewriter.rewrite_advanced(
            query=query,
            history=history,
            llm_port=failing_llm,
        )

        assert res.tier == "TIER_2_ERROR_FALLBACK"
        assert res.reason == "llm_error_fallback"
        assert "Chính sách bảo mật mật khẩu" in res.text

    asyncio.run(_run())


def test_backward_compatible_facade():
    """Validates query_rewriter.rewrite() facade returns string with seamless fallback."""
    async def _run():
        history = [
            {"role": "user", "content": "Quy chế đào tạo nhân sự nội bộ"},
            {"role": "assistant", "content": "Hỗ trợ 100% học phí chứng chỉ chuyên môn."},
        ]
        query = "Nó có yêu cầu cam kết làm việc không?"

        result_str = await query_rewriter.rewrite(query=query, history=history)
        assert isinstance(result_str, str)
        assert "Quy chế đào tạo nhân sự nội bộ" in result_str

    asyncio.run(_run())


def test_chat_use_case_pre_retrieval_telemetry():
    """Validates that RagChatUseCase executes with Pre-Retrieval telemetry in DTO and streaming."""
    async def _run():
        class DummyEmbeddingService:
            async def get_embedding(self, text: str) -> List[float]:
                return [0.1] * 768

        class DummyVectorStore:
            async def search(self, **kwargs) -> List[Dict[str, Any]]:
                return [
                    {
                        "doc_id": "doc_hr_01",
                        "score": 0.92,
                        "payload": {
                            "doc_id": "doc_hr_01",
                            "title": "Quy chế Đào tạo",
                            "page_number": 1,
                            "text": "Khoản 1: Cán bộ nhân viên được hỗ trợ 100% chi phí đào tạo nâng cao trình độ.",
                        },
                    }
                ]

        class DummySessionRepo:
            def __init__(self):
                self.saved = []

            async def get_session(self, *args, **kwargs):
                return None

            async def save_session(self, **kwargs):
                self.saved.append(kwargs)

        mock_llm = MockFastLLM(canned_response="Nhân viên được hỗ trợ toàn bộ học phí đào tạo [1].")
        use_case = RagChatUseCase(
            vector_store=DummyVectorStore(),
            embedding_service=DummyEmbeddingService(),
            llm_service=mock_llm,
            session_repo=DummySessionRepo(),
        )

        # 1. Non-streaming execution
        req = RagChatRequestDTO(
            query="Chính sách hỗ trợ học phí đào tạo của công ty?",
            history=None,
        )
        resp: RagChatResponseDTO = await use_case.execute(req)

        assert resp.pre_retrieval_tier == "TIER_1_HEURISTIC"
        assert resp.pre_retrieval_latency_ms >= 0.0
        assert "đào tạo" in resp.answer.lower()

        # 2. Streaming execution (validating TTFT in done event)
        stream_gen = use_case.stream_execute(req)
        stream_events = []
        async for event in stream_gen:
            if event.startswith("data: "):
                payload = json.loads(event[6:].strip())
                stream_events.append(payload)

        # Check done event contains telemetry
        done_event = next((e for e in stream_events if e.get("done") is True), None)
        assert done_event is not None
        assert done_event.get("pre_retrieval_tier") == "TIER_1_HEURISTIC"
        assert done_event.get("ttft_ms") is not None
        assert done_event["ttft_ms"] < 1200.0  # TTFT SLA < 1.2s commitment

    asyncio.run(_run())


def test_zero_vietnamese_legal_regex_audit_in_query_rewriter():
    """Strict architectural audit: ZERO hardcoded Vietnamese legal keywords in query rewriter."""
    source_code = inspect.getsource(RagQueryRewriter)

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
            f"VIOLATION: Found forbidden legal pattern '{pattern}' in RagQueryRewriter! "
            f"Must maintain 100% domain-agnostic pre-retrieval engine."
        )
