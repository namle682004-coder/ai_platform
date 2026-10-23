"""
Unit & Integration Tests for FR-006, RER-RAG-03:
Lost-in-the-Middle Context Re-ordering (U-shaped Attention Curve) and De-duplication.
"""

import asyncio
from typing import Any, Dict, List, Optional, Tuple

from solutions.rag.application.components.prompt_builder import RagPromptBuilder, prompt_builder
from solutions.rag.application.dtos import RagChatRequestDTO
from solutions.rag.application.use_cases.chat_use_case import RagChatUseCase
from solutions.rag.domain.ports import EmbeddingPort, LLMPort, SessionRepositoryPort, VectorStorePort


class DummyChunk:
    def __init__(self, doc_id: str, title: str, text: str, score: float, page_number: int = 1):
        self.doc_id = doc_id
        self.title = title
        self.text = text
        self.score = score
        self.page_number = page_number
        self.metadata = {}


def test_reorder_lost_in_middle_algorithm():
    """
    RER-RAG-03 DoD:
    Sắp xếp lại các chunk theo quy luật hình chữ U:
    - Chunk điểm cao nhất (Rank 1) đặt ở VỊ TRÍ ĐẦU TIÊN (Index 0).
    - Chunk điểm cao thứ nhì (Rank 2) đặt ở VỊ TRÍ CUỐI CÙNG (Index -1).
    - Các chunk còn lại đặt ở giữa.
    """
    builder = RagPromptBuilder()

    # Case N = 1
    assert builder.reorder_lost_in_middle(["A"]) == ["A"]

    # Case N = 2
    assert builder.reorder_lost_in_middle(["A", "B"]) == ["A", "B"]

    # Case N = 3: [A, B, C] -> A at start, B at end, C in middle -> [A, C, B]
    reordered_3 = builder.reorder_lost_in_middle(["A", "B", "C"])
    assert reordered_3 == ["A", "C", "B"]
    assert reordered_3[0] == "A"
    assert reordered_3[-1] == "B"

    # Case N = 4: [A, B, C, D] -> A at start, B at end -> [A, C, D, B]
    reordered_4 = builder.reorder_lost_in_middle(["A", "B", "C", "D"])
    assert reordered_4 == ["A", "C", "D", "B"]
    assert reordered_4[0] == "A"
    assert reordered_4[-1] == "B"

    # Case N = 5: [A, B, C, D, E] -> [A, C, E, D, B]
    reordered_5 = builder.reorder_lost_in_middle(["A", "B", "C", "D", "E"])
    assert reordered_5 == ["A", "C", "E", "D", "B"]
    assert reordered_5[0] == "A"
    assert reordered_5[-1] == "B"


def test_prompt_builder_places_best_chunks_at_boundaries():
    """
    Verifies that build_context_and_citations renders the U-shaped context
    so that LLM attention mechanism captures the top facts at start and end.
    """
    c1 = DummyChunk("doc_1", "Tài liệu 1 (Rank 1)", "Nội dung quan trọng nhất 1", 0.99)
    c2 = DummyChunk("doc_2", "Tài liệu 2 (Rank 2)", "Nội dung quan trọng nhì 2", 0.92)
    c3 = DummyChunk("doc_3", "Tài liệu 3 (Rank 3)", "Nội dung phụ 3", 0.85)

    reordered = prompt_builder.reorder_lost_in_middle([c1, c2, c3])
    assert reordered == [c1, c3, c2]

    citations, prompt = prompt_builder.build_context_and_citations(reordered)

    # In prompt text, chunk 1 appears first, chunk 2 appears last
    idx_c1 = prompt.find("Nội dung quan trọng nhất 1")
    idx_c3 = prompt.find("Nội dung phụ 3")
    idx_c2 = prompt.find("Nội dung quan trọng nhì 2")

    assert idx_c1 != -1 and idx_c2 != -1 and idx_c3 != -1
    assert idx_c1 < idx_c3 < idx_c2, "Chunk 1 must appear before Chunk 3, and Chunk 2 must appear at the end"


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
    async def get_session(self, *args, **kwargs):
        return None

    async def save_session(self, *args, **kwargs):
        return True

    async def append_message(self, *args, **kwargs):
        return True

    async def append_turn(self, *args, **kwargs):
        return True

    async def list_sessions(self, *args, **kwargs):
        return []

    async def delete_session(self, *args, **kwargs):
        return True

    async def update_title(self, *args, **kwargs):
        return True

    async def delete_message(self, *args, **kwargs):
        return True


class CapturingLLMService(LLMPort):
    def __init__(self):
        self.captured_messages = []

    async def generate(
        self,
        messages: List[Dict[str, str]],
        model: str,
        temperature: float = 0.2,
        max_tokens: int = 1024,
        authorization: Optional[str] = None,
    ) -> Tuple[str, int, int]:
        self.captured_messages = messages
        return "Trả lời tổng hợp [1] [2].", 100, 20

    async def stream_generate(self, *args, **kwargs):
        yield "token"


def test_use_case_applies_lost_in_middle_to_llm_prompt(monkeypatch):
    """
    Validates end-to-end that RagChatUseCase reorders valid candidates
    into U-shape before sending to the LLM.
    """
    async def _run():
        llm = CapturingLLMService()
        cand1 = {
            "id": 1,
            "score": 0.98,
            "text": "Dữ kiện Rank 1: Hà Nội là thủ đô.",
            "payload": {"doc_id": "d1", "title": "Doc 1", "text": "Dữ kiện Rank 1: Hà Nội là thủ đô.", "page_number": 1},
        }
        cand2 = {
            "id": 2,
            "score": 0.92,
            "text": "Dữ kiện Rank 2: TP.HCM là trung tâm kinh tế.",
            "payload": {"doc_id": "d2", "title": "Doc 2", "text": "Dữ kiện Rank 2: TP.HCM là trung tâm kinh tế.", "page_number": 1},
        }
        cand3 = {
            "id": 3,
            "score": 0.86,
            "text": "Dữ kiện Rank 3: Đà Nẵng là thành phố đáng sống.",
            "payload": {"doc_id": "d3", "title": "Doc 3", "text": "Dữ kiện Rank 3: Đà Nẵng là thành phố đáng sống.", "page_number": 1},
        }
        candidates = [cand1, cand2, cand3]

        from solutions.rag.application.components.reranker import cross_encoder_reranker
        monkeypatch.setattr(cross_encoder_reranker, "rerank", lambda **kwargs: candidates)

        vs = MockVectorStore(candidates)
        emb = MockEmbeddingService()
        repo = MockSessionRepo()
        use_case = RagChatUseCase(vs, emb, llm, repo)

        req = RagChatRequestDTO(
            query="Thông tin về các thành phố lớn tại Việt Nam",
            enable_hyde=False,
            combine_strategy="stuff",
        )

        await use_case.execute(req)

        # Inspect the system prompt received by LLM
        sys_prompt = next(m["content"] for m in llm.captured_messages if m["role"] == "system")

        pos_rank1 = sys_prompt.find("Hà Nội là thủ đô")
        pos_rank3 = sys_prompt.find("Đà Nẵng là thành phố đáng sống")
        pos_rank2 = sys_prompt.find("TP.HCM là trung tâm kinh tế")

        assert pos_rank1 != -1 and pos_rank3 != -1 and pos_rank2 != -1
        assert pos_rank1 < pos_rank3 < pos_rank2, "Prompt context must be re-ordered into U-shape: Rank 1 -> Rank 3 -> Rank 2"

    asyncio.run(_run())
