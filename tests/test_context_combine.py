"""
Unit and Integration Tests for RAG Context Combine Strategies (Slide 80 - TS. Lương Văn Thiện).
Verifies Stuff, Map-Reduce, and Refine pipelines for both non-streaming and streaming executions.
"""

import asyncio
import json
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple

import pytest

from solutions.rag.application.components.prompt_builder import REFUSAL_MESSAGE, RagPromptBuilder
from solutions.rag.application.dtos import RagChatRequestDTO, RagChatResponseDTO
from solutions.rag.application.use_cases.chat_use_case import CandidateWrapper, RagChatUseCase
from solutions.rag.domain.ports import EmbeddingPort, LLMPort, SessionRepositoryPort, VectorStorePort


class MockEmbeddingService(EmbeddingPort):
    async def get_embedding(self, text: str, model_alias: str = "embed-standard") -> List[float]:
        return [0.05] * 1024

    async def batch_get_embeddings(self, texts: List[str], model_alias: str = "embed-standard") -> List[List[float]]:
        return [[0.05] * 1024 for _ in texts]


class MockVectorStore(VectorStorePort):
    def __init__(self, candidates: List[Dict[str, Any]]):
        self._candidates = candidates

    async def ensure_collection(self) -> None:
        pass

    async def search(self, **kwargs: Any) -> List[Dict[str, Any]]:
        return self._candidates

    async def upsert_chunks(self, chunks: List[Any], **kwargs: Any) -> int:
        return len(chunks)

    async def delete_by_doc_id(self, doc_id: str, tenant_id: str) -> bool:
        return True


class MockSessionRepo(SessionRepositoryPort):
    def __init__(self):
        self.turns = []

    async def get_session(self, session_id: str, user_id: str, tenant_id: str) -> Optional[Dict[str, Any]]:
        return None

    async def save_session(
        self,
        session_id: str,
        user_id: str,
        tenant_id: str,
        title: str,
        messages: List[Dict[str, Any]],
    ) -> bool:
        return True

    async def append_message(
        self,
        session_id: str,
        user_id: str,
        tenant_id: str,
        message: Dict[str, Any],
        title: Optional[str] = None,
    ) -> bool:
        return True

    async def append_turn(
        self,
        session_id: str,
        user_id: str,
        tenant_id: str,
        user_msg: Dict[str, Any],
        assistant_msg: Dict[str, Any],
        title: Optional[str] = None,
    ) -> bool:
        self.turns.append((user_msg, assistant_msg))
        return True

    async def list_sessions(self, user_id: str, tenant_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        return []

    async def delete_session(self, session_id: str, user_id: str, tenant_id: str) -> bool:
        return True

    async def update_title(self, session_id: str, title: str, user_id: str, tenant_id: str) -> bool:
        return True

    async def delete_message(self, session_id: str, message_id: str, user_id: str, tenant_id: str) -> bool:
        return True


class MockLLMService(LLMPort):
    def __init__(self):
        self.calls: List[List[Dict[str, str]]] = []

    async def generate(
        self,
        messages: List[Dict[str, str]],
        model: str,
        temperature: float = 0.2,
        max_tokens: int = 1024,
        authorization: Optional[str] = None,
    ) -> Tuple[str, int, int]:
        self.calls.append(messages)
        sys_msg = next((m["content"] for m in messages if m["role"] == "system"), "")
        user_msg = next((m["content"] for m in messages if m["role"] == "user"), "")

        if "chuyên gia phân tích và trích xuất dữ kiện" in sys_msg:
            # Map phase response
            chunk_num = "1"
            if "ĐOẠN TÀI LIỆU [2]" in user_msg:
                chunk_num = "2"
            elif "ĐOẠN TÀI LIỆU [3]" in user_msg:
                chunk_num = "3"
            return f"Ý chính từ đoạn {chunk_num} [{chunk_num}].", 50, 20

        if "Tổng hợp các thông tin đã được trích xuất" in sys_msg or "Dưới đây là các thông tin và dữ kiện" in sys_msg:
            # Reduce phase response
            return "Tổng hợp toàn bộ các kết quả từ tài liệu [1] và [2].", 120, 60

        if "TINH CHỈNH/BỔ SUNG vào câu trả lời hiện tại" in sys_msg:
            # Refine step response
            return "Câu trả lời đã được tinh chỉnh cập nhật thêm ý [2].", 100, 40

        if "chuyên gia phân tích và đánh giá tài liệu" in sys_msg:
            # Map-rerank phase response
            chunk_num = "1"
            score = 95
            if "ĐOẠN TÀI LIỆU [2]" in user_msg:
                chunk_num = "2"
                score = 70
            elif "ĐOẠN TÀI LIỆU [3]" in user_msg:
                chunk_num = "3"
                score = 50
            return f"ĐIỂM: {score}\nCÂU_TRẢ_LỜI: Câu trả lời chính xác nhất từ đoạn {chunk_num} [{chunk_num}].", 60, 25

        # Default stuff response
        return "Câu trả lời mặc định theo cơ chế stuff [1].", 80, 30

    async def stream_generate(
        self,
        messages: List[Dict[str, str]],
        model: str,
        temperature: float = 0.2,
        max_tokens: int = 1024,
        authorization: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        self.calls.append(messages)
        yield "Phản "
        yield "hồi "
        yield "stream [1]."


@pytest.fixture
def sample_candidates() -> List[Dict[str, Any]]:
    return [
        {
            "doc_id": "doc_01",
            "score": 0.88,
            "payload": {
                "doc_id": "doc_01",
                "title": "Quy chế Tài chính",
                "page_number": 1,
                "text": "Điều 1: Quy định về công tác phí 500,000 VNĐ/ngày cho nhân viên.",
                "heading_path": "Chương I > Điều 1",
            },
        },
        {
            "doc_id": "doc_02",
            "score": 0.85,
            "payload": {
                "doc_id": "doc_02",
                "title": "Quy chế Phúc lợi",
                "page_number": 2,
                "text": "Điều 5: Phụ cấp lưu trú vùng sâu vùng xa thêm 200,000 VNĐ/ngày.",
                "heading_path": "Chương II > Điều 5",
            },
        },
    ]


def test_prompt_builder_map_reduce_and_refine(sample_candidates):
    pb = RagPromptBuilder()
    wrapped = [CandidateWrapper(c) for c in sample_candidates]

    # 1. Test Map Prompt
    map_msgs = pb.build_map_prompt(wrapped[0], "Công tác phí thế nào?", chunk_index=1)
    assert len(map_msgs) == 2
    assert "ĐOẠN TÀI LIỆU [1]" in map_msgs[1]["content"]
    assert "KHÔNG_CÓ_THÔNG_TIN_LIÊN_QUAN" in map_msgs[0]["content"]

    # 2. Test Reduce Prompt
    reduce_msgs = pb.build_reduce_prompt(
        query="Tổng hợp công tác phí",
        map_summaries=["[1] Công tác phí 500k.", "[2] Phụ cấp lưu trú 200k."],
    )
    assert len(reduce_msgs) >= 2
    assert "[1] Công tác phí 500k." in reduce_msgs[-1]["content"]
    assert "[2] Phụ cấp lưu trú 200k." in reduce_msgs[-1]["content"]

    # 3. Test Refine Initial and Step Prompts
    init_msgs = pb.build_refine_initial_prompt(wrapped[0], "Công tác phí thế nào?", chunk_index=1)
    assert "ĐOẠN TÀI LIỆU [1]" in init_msgs[-1]["content"]

    step_msgs = pb.build_refine_step_prompt(
        existing_answer="Đoạn 1 cho biết 500k [1].",
        next_chunk=wrapped[1],
        query="Công tác phí thế nào?",
        chunk_index=2,
    )
    assert "ĐOẠN TÀI LIỆU MỚI [2]" in step_msgs[1]["content"]
    assert "Đoạn 1 cho biết 500k [1]." in step_msgs[1]["content"]


def test_resolve_combine_strategy(sample_candidates):
    llm = MockLLMService()
    vs = MockVectorStore(sample_candidates)
    emb = MockEmbeddingService()
    repo = MockSessionRepo()
    use_case = RagChatUseCase(vs, emb, llm, repo)

    wrapped = [CandidateWrapper(c) for c in sample_candidates]

    # Explicit strategy overrides
    assert use_case._resolve_combine_strategy("map_reduce", "hỏi bình thường", wrapped) == "map_reduce"
    assert use_case._resolve_combine_strategy("refine", "hỏi bình thường", wrapped) == "refine"
    assert use_case._resolve_combine_strategy("map_rerank", "hỏi bình thường", wrapped) == "map_rerank"
    assert use_case._resolve_combine_strategy("stuff", "tổng hợp toàn bộ", wrapped) == "stuff"

    # Single chunk defaults to stuff even if requested map_reduce
    single_wrapped = [wrapped[0]]
    assert use_case._resolve_combine_strategy("auto", "hỏi bình thường", single_wrapped) == "stuff"

    # Auto-detection for summary keywords
    assert use_case._resolve_combine_strategy("auto", "Hãy tổng hợp toàn bộ các quy định công tác phí", wrapped) == "map_reduce"
    assert use_case._resolve_combine_strategy("auto", "Tóm tắt ngắn gọn", wrapped) == "map_reduce"
    assert use_case._resolve_combine_strategy("auto", "công tác phí bao nhiêu tiền?", wrapped) == "stuff"


def test_execute_with_map_reduce(sample_candidates):
    async def _run():
        llm = MockLLMService()
        vs = MockVectorStore(sample_candidates)
        emb = MockEmbeddingService()
        repo = MockSessionRepo()
        use_case = RagChatUseCase(vs, emb, llm, repo)

        req = RagChatRequestDTO(
            query="Hãy tổng hợp toàn bộ chế độ phụ cấp",
            combine_strategy="map_reduce",
            similarity_threshold=0.0,
        )

        resp: RagChatResponseDTO = await use_case.execute(req)

        assert resp.combine_strategy == "map_reduce"
        assert "Tổng hợp toàn bộ các kết quả" in resp.answer
        assert len(resp.citations) == 2
        # Verify that Map calls were made for both chunks + 1 Reduce call
        assert len(llm.calls) >= 3

    asyncio.run(_run())


def test_execute_with_refine(sample_candidates):
    async def _run():
        llm = MockLLMService()
        vs = MockVectorStore(sample_candidates)
        emb = MockEmbeddingService()
        repo = MockSessionRepo()
        use_case = RagChatUseCase(vs, emb, llm, repo)

        req = RagChatRequestDTO(
            query="Chi tiết quy trình công tác phí",
            combine_strategy="refine",
            similarity_threshold=0.0,
        )

        resp: RagChatResponseDTO = await use_case.execute(req)

        assert resp.combine_strategy == "refine"
        assert "Câu trả lời đã được tinh chỉnh" in resp.answer
        assert len(resp.citations) == 2
        # Initial call on chunk 1 + Refine call on chunk 2 (+ optional HyDE call)
        assert len(llm.calls) >= 2

    asyncio.run(_run())


def test_stream_execute_with_map_reduce(sample_candidates):
    async def _run():
        llm = MockLLMService()
        vs = MockVectorStore(sample_candidates)
        emb = MockEmbeddingService()
        repo = MockSessionRepo()
        use_case = RagChatUseCase(vs, emb, llm, repo)

        req = RagChatRequestDTO(
            query="Tóm tắt chế độ công tác phí",
            combine_strategy="map_reduce",
            stream=True,
            similarity_threshold=0.0,
        )

        events = []
        async for sse in use_case.stream_execute(req):
            events.append(sse)

        assert len(events) >= 2
        # Find the done event
        done_event = [e for e in events if '"done": true' in e.lower()][0]
        data = json.loads(done_event.replace("data: ", "").strip())
        assert data["done"] is True
        assert data["combine_strategy"] == "map_reduce"
        assert len(data["citations"]) == 2

    asyncio.run(_run())


def test_prompt_builder_map_rerank(sample_candidates):
    pb = RagPromptBuilder()
    wrapped = [CandidateWrapper(c) for c in sample_candidates]

    rerank_msgs = pb.build_map_rerank_prompt(wrapped[0], "Công tác phí thế nào?", chunk_index=1)
    assert len(rerank_msgs) == 2
    assert "ĐOẠN TÀI LIỆU [1]" in rerank_msgs[1]["content"]
    assert "chuyên gia phân tích và đánh giá tài liệu" in rerank_msgs[0]["content"]
    assert "ĐIỂM: <số nguyên từ 0 đến 100>" in rerank_msgs[0]["content"]


def test_execute_with_map_rerank(sample_candidates):
    async def _run():
        llm = MockLLMService()
        vs = MockVectorStore(sample_candidates)
        emb = MockEmbeddingService()
        repo = MockSessionRepo()
        use_case = RagChatUseCase(vs, emb, llm, repo)

        req = RagChatRequestDTO(
            query="Công tác phí bao nhiêu?",
            combine_strategy="map_rerank",
            similarity_threshold=0.0,
        )

        resp: RagChatResponseDTO = await use_case.execute(req)

        assert resp.combine_strategy == "map_rerank"
        assert "Câu trả lời chính xác nhất từ đoạn 1" in resp.answer
        # map_rerank isolates citations to the winning chunk
        assert len(resp.citations) == 1
        assert resp.citations[0].doc_id == "doc_01"
        # Evaluated both candidates concurrently
        assert len(llm.calls) >= 2

    asyncio.run(_run())


def test_stream_execute_with_map_rerank(sample_candidates):
    async def _run():
        llm = MockLLMService()
        vs = MockVectorStore(sample_candidates)
        emb = MockEmbeddingService()
        repo = MockSessionRepo()
        use_case = RagChatUseCase(vs, emb, llm, repo)

        req = RagChatRequestDTO(
            query="Công tác phí bao nhiêu?",
            combine_strategy="map_rerank",
            stream=True,
            similarity_threshold=0.0,
        )

        events = []
        async for sse in use_case.stream_execute(req):
            events.append(sse)

        assert len(events) >= 2
        done_event = [e for e in events if '"done": true' in e.lower()][0]
        data = json.loads(done_event.replace("data: ", "").strip())
        assert data["done"] is True
        assert data["combine_strategy"] == "map_rerank"
        assert len(data["citations"]) == 1
        assert data["citations"][0]["doc_id"] == "doc_01"

    asyncio.run(_run())


def test_anti_hallucination_gatekeeper_rejection():
    """Validates that Anti-Hallucination Gatekeeper (Slide 16) rejects low confidence queries (< 0.50) without calling LLM."""
    async def _run():
        low_candidates = [
            {
                "doc_id": "doc_noise",
                "score": 0.38,
                "payload": {
                    "doc_id": "doc_noise",
                    "title": "Tài liệu không liên quan",
                    "text": "Nội dung hoàn toàn không liên quan đến câu hỏi vũ trụ.",
                },
            }
        ]
        llm = MockLLMService()
        vs = MockVectorStore(low_candidates)
        emb = MockEmbeddingService()
        repo = MockSessionRepo()
        use_case = RagChatUseCase(vs, emb, llm, repo)

        req = RagChatRequestDTO(
            query="Bí quyết du hành vũ trụ đến sao Hỏa?",
        )

        resp: RagChatResponseDTO = await use_case.execute(req)

        assert resp.intent == "REFUSAL"
        assert resp.answer == REFUSAL_MESSAGE
        assert resp.citations == []
        assert len(llm.calls) == 0

    asyncio.run(_run())


