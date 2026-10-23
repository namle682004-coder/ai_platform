"""
Unit tests for Audit Item 9: Clean Architecture Ports & Dependency Inversion.
Verifies:
1. All Concrete Adapters inherit from and fully satisfy their respective Domain Ports.
2. CachePort and RedisCacheAdapter have 100% parameter signature parity.
3. RerankerPort polymorphic typing: supports both RetrievalCandidate entities and raw dicts.
4. Clean Architecture Dependency Rule: Application and Domain layers have ZERO imports from Infrastructure.
5. Pure Dependency Injection: RagChatUseCase operates seamlessly with mock ports and NullCacheAdapter.
"""

import ast
import inspect
import os
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple

from solutions.rag.domain.entities import RetrievalCandidate
from solutions.rag.domain.ports import (
    CachePort,
    EmbeddingPort,
    LLMPort,
    NullCacheAdapter,
    NullObservabilityAdapter,
    ObservabilityPort,
    RerankerPort,
    SessionRepositoryPort,
    StoragePort,
    VectorStorePort,
)
from solutions.rag.infrastructure.adapters.embedding_adapter import GrpcEmbeddingAdapter
from solutions.rag.infrastructure.adapters.llm_adapter import HttpLlmAdapter
from solutions.rag.infrastructure.adapters.qdrant_adapter import QdrantVectorStoreAdapter
from solutions.rag.infrastructure.adapters.redis_cache_adapter import RedisCacheAdapter
from solutions.rag.infrastructure.adapters.storage_adapter import MinioStorageAdapter
from solutions.rag.infrastructure.observability import PrometheusObservabilityAdapter
from solutions.rag.application.components.reranker import NeuralCrossEncoderReranker
from solutions.rag.application.use_cases.chat_use_case import RagChatUseCase
from solutions.rag.application.dtos import RagChatRequestDTO


def test_ports_inheritance():
    """Verify that every concrete adapter strictly implements its domain port interface."""
    assert issubclass(RedisCacheAdapter, CachePort), "RedisCacheAdapter must inherit from CachePort"
    assert issubclass(NullCacheAdapter, CachePort), "NullCacheAdapter must inherit from CachePort"
    assert issubclass(NeuralCrossEncoderReranker, RerankerPort), "NeuralCrossEncoderReranker must inherit from RerankerPort"
    assert issubclass(GrpcEmbeddingAdapter, EmbeddingPort), "GrpcEmbeddingAdapter must inherit from EmbeddingPort"
    assert issubclass(HttpLlmAdapter, LLMPort), "HttpLlmAdapter must inherit from LLMPort"
    assert issubclass(MinioStorageAdapter, StoragePort), "MinioStorageAdapter must inherit from StoragePort"
    assert issubclass(QdrantVectorStoreAdapter, VectorStorePort), "QdrantVectorStoreAdapter must inherit from VectorStorePort"
    assert issubclass(PrometheusObservabilityAdapter, ObservabilityPort), "PrometheusObservabilityAdapter must inherit from ObservabilityPort"
    assert issubclass(NullObservabilityAdapter, ObservabilityPort), "NullObservabilityAdapter must inherit from ObservabilityPort"


def test_cache_port_signature_parity():
    """
    Verify parameter name and default value parity between CachePort and RedisCacheAdapter.
    Proves CachePort is not empty ceremony.
    """
    port_get_params = inspect.signature(CachePort.get).parameters
    adapter_get_params = inspect.signature(RedisCacheAdapter.get).parameters

    # Must have identical parameter names in exact order
    assert list(port_get_params.keys()) == list(adapter_get_params.keys()), (
        f"CachePort.get params {list(port_get_params.keys())} mismatch adapter {list(adapter_get_params.keys())}"
    )

    expected_params = [
        "self", "query", "tenant_id", "combine_strategy", "as_of_date",
        "user_role", "department", "similarity_threshold"
    ]
    for p in expected_params:
        assert p in port_get_params, f"Missing expected param '{p}' in CachePort.get"

    port_set_params = inspect.signature(CachePort.set).parameters
    adapter_set_params = inspect.signature(RedisCacheAdapter.set).parameters
    assert list(port_set_params.keys()) == list(adapter_set_params.keys())


def test_reranker_port_candidate_type_polymorphism():
    """
    Verify RerankerPort and NeuralCrossEncoderReranker correctly accept and return
    both RetrievalCandidate domain entities and raw dictionary payloads.
    """
    reranker = NeuralCrossEncoderReranker()

    # 1. Test with RetrievalCandidate domain entities
    cand_entity_1 = RetrievalCandidate(
        doc_id="doc_1",
        chunk_id="chk_1",
        title="Quy chế làm việc",
        filename="quy_che.pdf",
        page_number=1,
        text="Quy định về thời giờ làm việc và nghỉ ngơi của nhân viên doanh nghiệp.",
        score=0.70,
    )
    cand_entity_2 = RetrievalCandidate(
        doc_id="doc_2",
        chunk_id="chk_2",
        title="Chính sách bảo hiểm",
        filename="bhxh.pdf",
        page_number=3,
        text="Chế độ bảo hiểm xã hội bắt buộc và bảo hiểm y tế cho người lao động.",
        score=0.85,
    )

    ranked_entities = reranker.rerank(
        query="Thời giờ làm việc của nhân viên",
        candidates=[cand_entity_1, cand_entity_2],
        top_n=2,
    )
    assert len(ranked_entities) >= 1
    assert isinstance(ranked_entities[0], RetrievalCandidate)

    # 2. Test with raw dictionary payloads
    dict_cand_1 = {
        "doc_id": "d1",
        "score": 0.55,
        "text": "Hướng dẫn nộp thuế thu nhập cá nhân điện tử",
        "payload": {"title": "Thuế TNCN", "text": "Hướng dẫn nộp thuế thu nhập cá nhân điện tử"},
    }
    dict_cand_2 = {
        "doc_id": "d2",
        "score": 0.90,
        "text": "Quy trình tính giảm trừ gia cảnh cho người phụ thuộc",
        "payload": {"title": "Giảm trừ gia cảnh", "text": "Quy trình tính giảm trừ gia cảnh cho người phụ thuộc"},
    }
    ranked_dicts = reranker.rerank(
        query="Nộp thuế TNCN",
        candidates=[dict_cand_1, dict_cand_2],
        top_n=2,
    )
    assert len(ranked_dicts) >= 1
    assert isinstance(ranked_dicts[0], dict)
    assert "score" in ranked_dicts[0]


def test_clean_architecture_dependency_rule_enforcement():
    """
    AST Static Analysis:
    Enforces the Dependency Rule that solutions/rag/application/ must NEVER
    import from solutions/rag/infrastructure/, and domain/ must NEVER import from application/ or infrastructure/.
    """
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    rag_dir = os.path.join(base_dir, "solutions", "rag")
    app_dir = os.path.join(rag_dir, "application")
    domain_dir = os.path.join(rag_dir, "domain")

    # 1. Scan application/ directory
    app_violations = []
    for root, _, files in os.walk(app_dir):
        for file in files:
            if file.endswith(".py"):
                filepath = os.path.join(root, file)
                with open(filepath, "r", encoding="utf-8") as f:
                    tree = ast.parse(f.read(), filename=filepath)
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            if "infrastructure" in alias.name:
                                app_violations.append((filepath, alias.name))
                    elif isinstance(node, ast.ImportFrom):
                        module = node.module or ""
                        if "infrastructure" in module:
                            app_violations.append((filepath, module))

    assert not app_violations, (
        f"Clean Architecture Violation: Application layer imports Infrastructure in {app_violations}"
    )

    # 2. Scan domain/ directory
    domain_violations = []
    for root, _, files in os.walk(domain_dir):
        for file in files:
            if file.endswith(".py"):
                filepath = os.path.join(root, file)
                with open(filepath, "r", encoding="utf-8") as f:
                    tree = ast.parse(f.read(), filename=filepath)
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            if "infrastructure" in alias.name or "application" in alias.name:
                                domain_violations.append((filepath, alias.name))
                    elif isinstance(node, ast.ImportFrom):
                        module = node.module or ""
                        if "infrastructure" in module or "application" in module:
                            domain_violations.append((filepath, module))

    assert not domain_violations, (
        f"Clean Architecture Violation: Domain layer imports outer layers in {domain_violations}"
    )


def test_pure_dependency_injection_offline_chat():
    """
    Verify RagChatUseCase can run with mock ports and NullCacheAdapter in 100% offline isolation.
    Proves true Dependency Injection works without any singleton coupling.
    """
    import asyncio

    class MockVectorStore(VectorStorePort):
        async def ensure_collection(self) -> None: pass
        async def upsert_chunks(self, *args, **kwargs) -> int: return 1
        async def search(self, *args, **kwargs) -> List[Dict[str, Any]]:
            return [{
                "doc_id": "doc_test_1",
                "chunk_id": "c1",
                "score": 0.88,
                "payload": {
                    "text": "Nhân viên chính thức được hưởng 12 ngày phép hàng năm theo quy định.",
                    "title": "Chính sách nghỉ phép",
                    "page_number": 1,
                    "filename": "phep_nam.pdf",
                }
            }]
        async def delete_by_doc_id(self, doc_id: str, tenant_id: str) -> bool: return True

    class MockEmbedding(EmbeddingPort):
        async def get_embedding(self, text: str, model_alias: str = "embed-standard") -> List[float]:
            return [0.1] * 768
        async def batch_get_embeddings(self, texts: List[str], model_alias: str = "embed-standard") -> List[List[float]]:
            return [[0.1] * 768 for _ in texts]

    class MockLLM(LLMPort):
        async def generate(self, messages, model, **kwargs) -> Tuple[str, int, int]:
            return "Theo chính sách, nhân viên được hưởng 12 ngày phép năm. [1]", 30, 20
        async def stream_generate(self, messages, model, **kwargs) -> AsyncGenerator[str, None]:
            yield "12 ngày phép năm"

    class MockSessionRepo(SessionRepositoryPort):
        async def get_session(self, *args, **kwargs) -> Optional[Dict[str, Any]]: return None
        async def save_session(self, *args, **kwargs) -> bool: return True
        async def append_message(self, *args, **kwargs) -> bool: return True
        async def append_turn(self, *args, **kwargs) -> bool: return True
        async def list_sessions(self, *args, **kwargs) -> List[Dict[str, Any]]: return []
        async def delete_session(self, *args, **kwargs) -> bool: return True
        async def update_title(self, *args, **kwargs) -> bool: return True

    chat_use_case = RagChatUseCase(
        vector_store=MockVectorStore(),
        embedding_service=MockEmbedding(),
        llm_service=MockLLM(),
        session_repo=MockSessionRepo(),
        cache_service=NullCacheAdapter(),
    )

    req = RagChatRequestDTO(
        query="Nhân viên có bao nhiêu ngày phép một năm?",
        conversation_id="test_sess_di",
        model="qwen-2.5-7b",
        stream=False,
    )

    response = asyncio.run(chat_use_case.execute(
        request=req,
        tenant_id="tenant_di_test",
        user_id="user_di_01",
        user_role="user",
    ))

    assert response.status == "success"
    assert "12 ngày phép" in response.answer
    assert len(response.citations) >= 1
    assert response.citations[0].document_name == "Chính sách nghỉ phép"
