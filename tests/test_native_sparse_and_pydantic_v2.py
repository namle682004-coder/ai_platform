"""
Test Suite for Technical Debt Resolution:
1. Pydantic V2 Native Settings (Zero Deprecation Warnings)
2. Qdrant Native On-Disk Sparse Vector Search & BM25 Scoring
3. Falsification Adversarial Tests for Edge Cases & Tenancy Isolation
"""

import os
import warnings
import pytest
from solutions.rag.config import RagSolutionSettings
from solutions.rag.infrastructure.adapters.qdrant_adapter import QdrantVectorStoreAdapter


def test_pydantic_v2_native_zero_warnings():
    """Falsification test: Ensure zero deprecation warnings emitted by RagSolutionSettings."""
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        settings = RagSolutionSettings()
        # Verify default properties
        assert settings.chunk_size_chars == 900
        assert settings.parent_chunk_size_chars == 3600
        assert settings.collection_name in ("aip_knowledge_base", "rag_documents")
        
        # Filter warnings originating from solutions/rag/config.py
        rag_warnings = [item for item in w if "solutions/rag/config.py" in str(item.filename)]
        assert len(rag_warnings) == 0, f"Expected 0 deprecation warnings, got: {rag_warnings}"


def test_pydantic_v2_environment_override():
    """Verify that environment variables cleanly override settings in Pydantic V2."""
    os.environ["RAG_CHUNK_SIZE"] = "1200"
    os.environ["RAG_PARENT_CHUNK_SIZE"] = "4800"
    try:
        custom_settings = RagSolutionSettings()
        assert custom_settings.chunk_size_chars == 1200
        assert custom_settings.parent_chunk_size_chars == 4800
    finally:
        os.environ.pop("RAG_CHUNK_SIZE", None)
        os.environ.pop("RAG_PARENT_CHUNK_SIZE", None)


def test_compute_sparse_vector_deterministic_and_bounded():
    """Verify deterministic token hash indices and BM25 saturation weights."""
    text1 = "Cuộc họp ngày 25-09 xác định 2 mục tiêu chính."
    vec1 = QdrantVectorStoreAdapter.compute_sparse_vector(text1)
    
    assert "indices" in vec1 and "values" in vec1
    assert len(vec1["indices"]) == len(vec1["values"])
    assert len(vec1["indices"]) > 0
    
    # Determinism: identical text must produce identical vector
    vec2 = QdrantVectorStoreAdapter.compute_sparse_vector(text1)
    assert vec1["indices"] == vec2["indices"]
    assert vec1["values"] == vec2["values"]
    
    # Values must be non-negative and finite
    for val in vec1["values"]:
        assert val > 0.0
        assert val < 10.0


def test_compute_sparse_vector_adversarial_inputs():
    """Adversarial stress test on edge-case inputs."""
    # 1. Empty string
    empty_vec = QdrantVectorStoreAdapter.compute_sparse_vector("")
    assert empty_vec == {"indices": [], "values": []}
    
    # 2. Pure whitespace and punctuation
    punct_vec = QdrantVectorStoreAdapter.compute_sparse_vector("   !@#$%^&*()_+=-~`<>?:\"{}[]   ")
    assert punct_vec == {"indices": [], "values": []}
    
    # 3. Single character words (filtered by len >= 2)
    single_char_vec = QdrantVectorStoreAdapter.compute_sparse_vector("a b c d e f")
    assert single_char_vec == {"indices": [], "values": []}
    
    # 4. Long repetitive document (verify term saturation)
    rep_text = "thông_tin " * 500
    rep_vec = QdrantVectorStoreAdapter.compute_sparse_vector(rep_text)
    assert len(rep_vec["indices"]) == 1
    # BM25 term saturation ensures weight does not blow up to 500
    assert rep_vec["values"][0] < 5.0


@pytest.mark.anyio
async def test_native_sparse_and_hybrid_search_live():
    """Live integration test against Qdrant collection with dual dense + sparse schema."""
    adapter = QdrantVectorStoreAdapter(collection_name="aip_knowledge_base")
    
    # Test query that has exact keywords in indexed documents
    results = await adapter.search_sparse_keywords(
        query_text="Đánh giá & Xếp loại Chất lượng ĐVSNCL và Viên chức",
        tenant_id="global",
        top_k=5,
    )
    assert isinstance(results, list)
    assert len(results) > 0
    
    top_hit = results[0]
    assert "id" in top_hit
    assert "score" in top_hit
    assert "DG233-BRD" in top_hit.get("payload", {}).get("title", "")
    assert top_hit.get("sparse_rank") == 1
