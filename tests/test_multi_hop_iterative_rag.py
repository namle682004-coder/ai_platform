"""
Unit and Integration Tests for Multi-Hop Reasoning & Iterative RAG (Trụ Cột 5 - Slide 94–103).

Validates:
1. Zero hardcoded Vietnamese legal regex audit.
2. Query decomposition rules (Comparative, Sequential, Speculative LLM Fallback).
3. Iterative query bridging with entity linkage.
4. Two-hop iterative retrieval execution and CoT prompt synthesis in RagChatUseCase.
5. Streaming SSE multi-hop telemetry.
6. Clean single-hop fallback and client override controls.
"""

import asyncio
import inspect
import json
import re
from typing import Any, AsyncGenerator, Dict, List, Tuple


from solutions.rag.application.components.prompt_builder import REFUSAL_MESSAGE
from solutions.rag.application.components.query_decomposer import (
    QueryDecomposer,
)
from solutions.rag.application.dtos import (
    RagChatRequestDTO,
    RagChatResponseDTO,
)
from solutions.rag.application.use_cases.chat_use_case import RagChatUseCase


# =====================================================================
# Test 1: Zero Vietnamese Legal Regex Audit (Hard Constraint)
# =====================================================================

def test_zero_vietnamese_legal_regex_audit_in_query_decomposer():
    """
    Validates that QueryDecomposer source code contains ZERO hardcoded Vietnamese
    legal regex keywords (Chương, Điều, Khoản, Mục).
    Ensures domain-agnostic and format-agnostic operation.
    """
    source_code = inspect.getsource(QueryDecomposer)

    # Strictly forbidden legal keywords
    forbidden_patterns = [
        r"Chương\s+",
        r"Điều\s+",
        r"Khoản\s+",
        r"Mục\s+",
        r"VIETNAMESE_HEADING",
    ]
    found_violations = []

    for pattern in forbidden_patterns:
        if re.search(pattern, source_code, re.IGNORECASE):
            found_violations.append(pattern)

    assert not found_violations, (
        f"VIOLATION: Found hardcoded Vietnamese legal keywords in query_decomposer.py: {found_violations}. "
        "System must be 100% domain-agnostic!"
    )


# =====================================================================
# Test 2: Multi-Hop Detection Rules (should_decompose)
# =====================================================================

def test_query_decomposer_should_decompose_rules():
    """Validates selective triggering rules for multi-hop decomposition."""
    decomposer = QueryDecomposer()

    # Comparative queries -> Auto-activate
    assert decomposer.should_decompose("So sánh chính sách WFH và chính sách làm việc tại văn phòng") is True
    assert decomposer.should_decompose("Sự khác biệt giữa nhân viên thử việc và nhân viên chính thức") is True
    assert decomposer.should_decompose("Điểm giống và khác giữa REST API và GraphQL") is True
    assert decomposer.should_decompose("Compare Python asyncio and Golang goroutines") is True
    assert decomposer.should_decompose("Difference between Docker and Kubernetes") is True
    assert decomposer.should_decompose("PostgreSQL vs MongoDB database architecture") is True

    # Sequential / Conjunction queries -> Auto-activate
    assert decomposer.should_decompose("Quy trình xin cấp phép thiết bị và đồng thời thủ tục thanh toán chi phí") is True
    assert decomposer.should_decompose("Tiêu chuẩn đánh giá KPI đồng thời cho biết hạn nộp báo cáo quý") is True
    assert decomposer.should_decompose("Ai là người phụ trách dự án Alpha và sau đó ai sẽ nghiệm thu?") is True

    # Single-hop / Standard queries -> Bypass multi-hop
    assert decomposer.should_decompose("Chính sách WFH") is False
    assert decomposer.should_decompose("Quy trình công tác phí?") is False
    assert decomposer.should_decompose("Cách cấu hình MinIO S3 bucket?") is False
    assert decomposer.should_decompose("Tổng hợp chi phí đào tạo") is False
    assert decomposer.should_decompose("WFH là gì?") is False


# =====================================================================
# Test 3: Heuristic Decomposition for Comparative Queries
# =====================================================================

def test_heuristic_decomposition_comparative():
    """Validates ultra-fast heuristic decomposition for comparative patterns (< 1ms)."""
    decomposer = QueryDecomposer()

    # 1. So sánh X và Y
    res1 = decomposer.decompose_heuristic("So sánh React và Vue")
    assert res1 is not None
    assert res1.is_multi_hop is True
    assert res1.strategy == "COMPARATIVE"
    assert len(res1.sub_queries) == 2
    assert "React" in res1.sub_queries[0]
    assert "Vue" in res1.sub_queries[1]
    assert res1.latency_ms < 50.0

    # 2. Sự khác biệt giữa X và Y
    res2 = decomposer.decompose_heuristic("Sự khác biệt giữa PostgreSQL và MySQL")
    assert res2 is not None
    assert res2.is_multi_hop is True
    assert res2.strategy == "COMPARATIVE"
    assert "PostgreSQL" in res2.sub_queries[0]
    assert "MySQL" in res2.sub_queries[1]

    # 3. English: Compare X and Y
    res3 = decomposer.decompose_heuristic("Compare Docker and Podman container engines")
    assert res3 is not None
    assert res3.is_multi_hop is True
    assert res3.strategy == "COMPARATIVE"

    # 4. X vs Y
    res4 = decomposer.decompose_heuristic("FastAPI vs Django framework performance")
    assert res4 is not None
    assert res4.is_multi_hop is True
    assert res4.strategy == "COMPARATIVE"


# =====================================================================
# Test 4: Heuristic Decomposition for Sequential / Conjunction Queries
# =====================================================================

def test_heuristic_decomposition_sequential():
    """Validates heuristic decomposition for sequential conjunctions."""
    decomposer = QueryDecomposer()

    query = "Quy trình đăng ký nghỉ phép và đồng thời chính sách hưởng lương trong thời gian nghỉ?"
    res = decomposer.decompose_heuristic(query)

    assert res is not None
    assert res.is_multi_hop is True
    assert res.strategy == "SEQUENTIAL"
    assert len(res.sub_queries) == 2
    assert "Quy trình đăng ký nghỉ phép" in res.sub_queries[0]
    assert "chính sách hưởng lương" in res.sub_queries[1]


# =====================================================================
# Test 5: Speculative Async LLM Decomposition Fallback
# =====================================================================

def test_speculative_llm_decomposition():
    """Validates speculative LLM fallback when heuristics do not match cleanly."""
    async def _run():
        class MockDecomposeLLM:
            def __init__(self):
                self.calls = []

            async def generate(self, messages, **kwargs):
                self.calls.append(messages)
                canned = json.dumps({
                    "is_multi_hop": True,
                    "sub_queries": [
                        "Dự án Titan do ai làm chủ nhiệm?",
                        "Chủ nhiệm dự án Titan thuộc bộ phận nào?",
                    ]
                })
                return canned, 25, 30

        mock_llm = MockDecomposeLLM()
        decomposer = QueryDecomposer()

        query = "Cho tôi biết ai làm chủ nhiệm dự án Titan và vị này thuộc bộ phận nào?"
        res = await decomposer.decompose(query, llm_port=mock_llm)

        assert res.is_multi_hop is True
        assert res.strategy == "LLM_DECOMPOSED"
        assert len(res.sub_queries) == 2
        assert "chủ nhiệm" in res.sub_queries[0]
        assert "bộ phận" in res.sub_queries[1]
        assert len(mock_llm.calls) == 1

    asyncio.run(_run())


def test_speculative_llm_decomposition_timeout_fallback():
    """Validates graceful fallback to single-hop when LLM decomposition times out or fails."""
    async def _run():
        class MockTimeoutLLM:
            async def generate(self, *args, **kwargs):
                await asyncio.sleep(0.5)
                return "{}", 10, 10

        decomposer = QueryDecomposer()
        res = await decomposer.decompose(
            "Câu hỏi phức tạp về kiến trúc hệ thống phân tán",
            llm_port=MockTimeoutLLM(),
            timeout=0.05,
        )

        assert res.is_multi_hop is False
        assert res.strategy == "SINGLE_HOP"
        assert len(res.sub_queries) == 1

    asyncio.run(_run())


# =====================================================================
# Test 6: Iterative Bridging Step
# =====================================================================

def test_iterative_bridging_query():
    """Validates bridging of anaphoric pronouns with context from Hop 1."""
    decomposer = QueryDecomposer()

    sub_q2 = "Người đó hiện đang công tác tại phòng ban nào?"
    hop1_candidates = [
        {
            "doc_id": "doc_lead_01",
            "score": 0.95,
            "payload": {
                "title": "Hồ sơ Lãnh đạo Nguyễn Văn A",
                "text": "Ông Nguyễn Văn A là Giám đốc phụ trách Kỹ thuật hạ tầng.",
            },
        }
    ]

    bridged = decomposer.bridge_query(sub_q2, hop1_candidates)
    assert "Hồ sơ Lãnh đạo Nguyễn Văn A" in bridged
    assert "người đó" in bridged.lower()


# =====================================================================
# Test 7 & 8: End-to-End Multi-Hop Execution in RagChatUseCase
# =====================================================================

class MockMultiHopLLM:
    """Mock LLM simulating Multi-Hop CoT generation."""

    def __init__(self, canned_answer: str = "Sau khi phân tích dữ kiện từ 2 bước, dưới đây là bản so sánh chi tiết:"):
        self.canned_answer = canned_answer
        self.calls: List[List[Dict[str, str]]] = []

    async def generate(self, messages: List[Dict[str, str]], **kwargs) -> Tuple[str, int, int]:
        self.calls.append(messages)
        return self.canned_answer, 50, 40

    async def stream_generate(self, messages: List[Dict[str, str]], **kwargs) -> AsyncGenerator[str, None]:
        self.calls.append(messages)
        for token in ["So ", "sánh ", "bước ", "1 ", "và ", "bước ", "2 [1][2]."]:
            yield token


class MockMultiHopVectorStore:
    """Mock Vector Store returning different candidates per search query."""

    def __init__(self):
        self.searches = []

    async def search(self, **kwargs) -> List[Dict[str, Any]]:
        query_text = kwargs.get("query_text", "")
        self.searches.append(query_text)

        if "react" in query_text.lower():
            return [
                {
                    "doc_id": "doc_react_01",
                    "score": 0.92,
                    "payload": {
                        "doc_id": "doc_react_01",
                        "title": "Tài liệu React",
                        "page_number": 1,
                        "text": "React là thư viện UI dạng component-based được phát triển bởi Meta.",
                    },
                }
            ]
        elif "vue" in query_text.lower():
            return [
                {
                    "doc_id": "doc_vue_01",
                    "score": 0.91,
                    "payload": {
                        "doc_id": "doc_vue_01",
                        "title": "Tài liệu Vue",
                        "page_number": 2,
                        "text": "Vue là framework tiến bộ với cú pháp SFC và hệ thống reactivity linh hoạt.",
                    },
                }
            ]
        else:
            return [
                {
                    "doc_id": "doc_general_01",
                    "score": 0.88,
                    "payload": {
                        "doc_id": "doc_general_01",
                        "title": "Tài liệu Tổng quan",
                        "page_number": 1,
                        "text": "Tài liệu tổng quan chung về hệ thống.",
                    },
                }
            ]


class MockEmbeddingService:
    async def get_embedding(self, text: str) -> List[float]:
        return [0.05] * 768


class MockSessionRepo:
    async def get_session(self, *args, **kwargs):
        return None

    async def save_session(self, **kwargs):
        pass


def test_rag_chat_use_case_multi_hop_comparative_flow():
    """Validates complete multi-hop execution flow for comparative queries."""
    async def _run():
        mock_llm = MockMultiHopLLM(
            canned_answer="So sánh giữa React và Vue: React dùng JSX [1], trong khi Vue dùng SFC template [2]."
        )
        vec_store = MockMultiHopVectorStore()

        use_case = RagChatUseCase(
            vector_store=vec_store,
            embedding_service=MockEmbeddingService(),
            llm_service=mock_llm,
            session_repo=MockSessionRepo(),
        )

        req = RagChatRequestDTO(
            query="So sánh React và Vue",
            history=None,
        )

        resp: RagChatResponseDTO = await use_case.execute(req)

        assert resp.is_multi_hop is True
        assert resp.hops_executed == 2
        assert resp.intent == "QA_MULTIHOP_COT"
        assert resp.combine_strategy == "multihop_cot"
        assert len(resp.sub_queries) == 2
        assert len(resp.citations) == 2

        # Check citations from both hops
        doc_ids = [c.doc_id for c in resp.citations]
        assert "doc_react_01" in doc_ids
        assert "doc_vue_01" in doc_ids

        # Check that 2 vector searches occurred (one for React, one for Vue)
        assert len(vec_store.searches) == 2
        searches_str = " ".join(vec_store.searches).lower()
        assert "react" in searches_str
        assert "vue" in searches_str

    asyncio.run(_run())


def test_rag_chat_use_case_multi_hop_refusal():
    """Validates refusal guardrail when neither hop finds valid chunks."""
    async def _run():
        class EmptyVectorStore:
            async def search(self, **kwargs):
                return []

        use_case = RagChatUseCase(
            vector_store=EmptyVectorStore(),
            embedding_service=MockEmbeddingService(),
            llm_service=MockMultiHopLLM(),
            session_repo=MockSessionRepo(),
        )

        req = RagChatRequestDTO(
            query="So sánh công nghệ siêu lượng tử và máy tính sinh học",
            similarity_threshold=0.5,
        )

        resp = await use_case.execute(req)

        assert resp.answer == REFUSAL_MESSAGE
        assert resp.intent == "REFUSAL"
        assert resp.is_multi_hop is True
        assert len(resp.citations) == 0

    asyncio.run(_run())


def test_rag_chat_use_case_multi_hop_streaming():
    """Validates streaming SSE output for multi-hop execution."""
    async def _run():
        mock_llm = MockMultiHopLLM()
        vec_store = MockMultiHopVectorStore()

        use_case = RagChatUseCase(
            vector_store=vec_store,
            embedding_service=MockEmbeddingService(),
            llm_service=mock_llm,
            session_repo=MockSessionRepo(),
        )

        req = RagChatRequestDTO(
            query="So sánh React và Vue",
            stream=True,
        )

        events = []
        async for chunk in use_case.stream_execute(req):
            events.append(chunk)

        # Parse SSE events
        done_event = None
        tokens = []
        for e in events:
            if e.startswith("data: "):
                payload = json.loads(e[6:].strip())
                if payload.get("done"):
                    done_event = payload
                elif "token" in payload:
                    tokens.append(payload["token"])

        assert len(tokens) > 0
        assert done_event is not None
        assert done_event.get("is_multi_hop") is True
        assert done_event.get("hops_executed") == 2
        assert done_event.get("combine_strategy") == "multihop_cot"
        assert len(done_event.get("citations", [])) == 2

    asyncio.run(_run())


def test_rag_chat_use_case_multi_hop_client_override():
    """Validates client override controls (multi_hop=False to force bypass)."""
    async def _run():
        mock_llm = MockMultiHopLLM(canned_answer="Trả lời dạng đơn bước.")
        vec_store = MockMultiHopVectorStore()

        use_case = RagChatUseCase(
            vector_store=vec_store,
            embedding_service=MockEmbeddingService(),
            llm_service=mock_llm,
            session_repo=MockSessionRepo(),
        )

        # Force bypass multi-hop via multi_hop=False
        req = RagChatRequestDTO(
            query="So sánh React và Vue",
            multi_hop=False,
        )

        resp = await use_case.execute(req)

        # Verify multi_hop is bypassed
        assert resp.is_multi_hop is False
        assert resp.hops_executed == 1
        assert resp.intent != "QA_MULTIHOP_COT"

    asyncio.run(_run())
