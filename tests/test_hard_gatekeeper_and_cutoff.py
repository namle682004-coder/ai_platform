"""
Unit & Integration Tests for FR-005, FR-GEN-04, RER-RAG-02:
Hard Gatekeeper, Circuit-Breaker (< 50ms), and Grounded Refusal.
"""

import asyncio
import json
import time
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple

from solutions.rag.application.components.prompt_builder import REFUSAL_MESSAGE
from solutions.rag.application.dtos import (
    CONFIDENCE_GATE_MIN_THRESHOLD,
    DEFAULT_CONFIDENCE_THRESHOLD,
    RagChatRequestDTO,
    RagChatResponseDTO,
)
from solutions.rag.application.use_cases.chat_use_case import RagChatUseCase
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

    async def append_message(self, *args, **kwargs) -> bool:
        return True

    async def append_turn(self, session_id, user_id, tenant_id, user_msg, assistant_msg, title=None) -> bool:
        self.turns.append((user_msg, assistant_msg))
        return True

    async def list_sessions(self, user_id, tenant_id, limit=50):
        return []

    async def delete_session(self, session_id, user_id, tenant_id):
        return True

    async def update_title(self, session_id, title, user_id, tenant_id):
        return True

    async def delete_message(self, session_id, message_id, user_id, tenant_id):
        return True


class MockLLMService(LLMPort):
    def __init__(self):
        self.calls: List[List[Dict[str, str]]] = []
        self.stream_calls: List[List[Dict[str, str]]] = []

    async def generate(
        self,
        messages: List[Dict[str, str]],
        model: str,
        temperature: float = 0.2,
        max_tokens: int = 1024,
        authorization: Optional[str] = None,
    ) -> Tuple[str, int, int]:
        self.calls.append(messages)
        return "Grounded answer [1].", 20, 10

    async def stream_generate(
        self,
        messages: List[Dict[str, str]],
        model: str,
        temperature: float = 0.2,
        max_tokens: int = 1024,
        authorization: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        self.stream_calls.append(messages)
        yield "Grounded "
        yield "answer [1]."


def test_confidence_threshold_constants():
    """Validates that production confidence threshold defaults to 0.75."""
    assert CONFIDENCE_GATE_MIN_THRESHOLD == 0.75
    assert DEFAULT_CONFIDENCE_THRESHOLD == 0.75


def test_circuit_breaker_triggers_on_low_score_chunk():
    """
    RER-RAG-02 DoD:
    When candidate score is below 0.75 (e.g. 0.72 from OOD probation trap),
    Circuit-Breaker MUST trigger instantly without calling LLM.
    """
    async def _run():
        llm = MockLLMService()
        # Candidate with low score (0.72)
        candidates = [
            {
                "id": 1,
                "score": 0.72,
                "text": "Kế hoạch thử việc lập trình viên Python 8 tuần...",
                "payload": {
                    "doc_id": "doc_hr_probation",
                    "title": "Kế hoạch thử việc",
                    "text": "Kế hoạch thử việc lập trình viên Python 8 tuần...",
                    "page_number": 1,
                },
            }
        ]
        vs = MockVectorStore(candidates)
        emb = MockEmbeddingService()
        repo = MockSessionRepo()
        use_case = RagChatUseCase(vs, emb, llm, repo)

        req = RagChatRequestDTO(
            query="Bí quyết du hành vũ trụ đến sao Hỏa là gì?",
            enable_hyde=False,
        )

        # The SLA covers the gate, not the one-off model load: warm the default reranker first
        # so the result does not depend on whether another test already loaded it.
        from solutions.rag.application.components.reranker import cross_encoder_reranker
        cross_encoder_reranker.warmup()

        start_t = time.time()
        resp: RagChatResponseDTO = await use_case.execute(req)
        elapsed_ms = (time.time() - start_t) * 1000

        # Must trigger refusal
        assert resp.answer == REFUSAL_MESSAGE
        assert resp.intent == "REFUSAL"
        assert resp.circuit_breaker_triggered is True
        assert resp.is_refusal is True
        assert len(resp.citations) == 0

        # Zero LLM generation calls
        assert len(llm.calls) == 0

        # Fast execution (< 100ms in test environment)
        assert elapsed_ms < 100

    asyncio.run(_run())


def test_circuit_breaker_triggers_on_streaming():
    """
    RER-RAG-02 DoD:
    Streaming chat also triggers instant refusal and telemetry flag on low score.
    """
    async def _run():
        llm = MockLLMService()
        candidates = [
            {
                "id": 1,
                "score": 0.65,
                "text": "Tài liệu không liên quan...",
                "payload": {
                    "doc_id": "doc_unrelated",
                    "title": "Không liên quan",
                    "text": "Tài liệu không liên quan...",
                    "page_number": 1,
                },
            }
        ]
        vs = MockVectorStore(candidates)
        emb = MockEmbeddingService()
        repo = MockSessionRepo()
        use_case = RagChatUseCase(vs, emb, llm, repo)

        req = RagChatRequestDTO(
            query="Mức trợ cấp thuê nhà New York 2026?",
            stream=True,
            enable_hyde=False,
        )

        events = []
        async for chunk in use_case.stream_execute(req):
            events.append(chunk)

        assert len(events) >= 2
        # First event is refusal message token
        token_payload = json.loads(events[0].replace("data: ", "").strip())
        assert token_payload.get("token") == REFUSAL_MESSAGE

        # Done event has telemetry
        done_payload = json.loads(events[-1].replace("data: ", "").strip())
        assert done_payload.get("circuit_breaker_triggered") is True
        assert done_payload.get("is_refusal") is True
        assert done_payload.get("citations") == []

        # Zero LLM stream calls
        assert len(llm.stream_calls) == 0

    asyncio.run(_run())


def test_gatekeeper_allows_high_score_chunk():
    """
    When candidate score is >= 0.75 (e.g. 0.95), Circuit-Breaker does NOT trigger.
    LLM is called with grounded context.
    """
    async def _run():
        llm = MockLLMService()
        candidates = [
            {
                "id": 1,
                "score": 0.95,
                "text": "Hai bên đã ký kết 11 văn kiện hợp tác...",
                "payload": {
                    "doc_id": "doc_diplomacy",
                    "title": "Biên bản hợp tác",
                    "text": "Hai bên đã ký kết 11 văn kiện hợp tác...",
                    "page_number": 1,
                },
            }
        ]
        vs = MockVectorStore(candidates)
        emb = MockEmbeddingService()
        repo = MockSessionRepo()
        use_case = RagChatUseCase(vs, emb, llm, repo)

        req = RagChatRequestDTO(
            query="Các văn kiện hợp tác nào đã được ký kết?",
        )

        resp: RagChatResponseDTO = await use_case.execute(req)

        assert resp.circuit_breaker_triggered is False
        assert resp.is_refusal is False
        assert len(llm.calls) == 1
        assert len(resp.citations) == 1
        assert resp.citations[0].doc_id == "doc_diplomacy"

    asyncio.run(_run())
