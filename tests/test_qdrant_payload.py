"""
Unit and integration test suite for ING-RAG-03:
Hierarchical Breadcrumb Injection & Metadata Payload Indexing.

DoD Verification:
1. Short text or isolated numbers match queries thanks to keywords in the [Ngữ cảnh: {heading_path}] prefix.
2. Qdrant payload contains: doc_id, chunk_id, parent_id, heading_path, content_type, token_count.
   Filters support content_type ('text', 'table', 'code') and heading_path.
3. Breadcrumb injection maintains content integrity without corrupting line numbers or text structure.
"""

import asyncio
import pytest
import httpx
from common.chunking import ChunkerFactory
from solutions.rag.domain.entities import DocumentChunk, ParsedDocument, ParsedPage
from solutions.rag.application.components.chunker import DocumentChunker
from solutions.rag.infrastructure.adapters.qdrant_adapter import QdrantVectorStoreAdapter


def test_standardized_metadata_chunker():
    """Verify common chunker generates standardized metadata fields."""
    chunker = ChunkerFactory.create("hybrid")
    sample_text = (
        "CHƯƠNG I: QUY ĐỊNH CHUNG\n\n"
        "Điều 1. Phạm vi điều chỉnh\n"
        "Quy chế này quy định về việc quản lý và vận hành hệ thống thông tin của ngân hàng."
    )
    chunks = chunker.split_text(sample_text)
    assert len(chunks) > 0
    first_chunk = chunks[0]
    meta = first_chunk["metadata"]

    assert "heading" in meta
    assert "content_type" in meta
    assert "strategy" in meta
    assert "char_length" in meta
    assert "token_count" in meta
    assert meta["char_length"] > 0
    assert meta["token_count"] > 0


def test_ing_rag_03_breadcrumb_injection_and_keyword_matching():
    """
    ING-RAG-03 DoD 1 & DoD 3:
    - [Ngữ cảnh: {heading_path}] injected into first line of each child chunk.
    - Isolated numbers/short sentences match queries via keywords in the breadcrumb prefix.
    - Original text lines remain intact and non-distorted.
    """
    raw_doc = (
        "# QUY CHẾ TÀI CHÍNH NĂM 2026\n\n"
        "## Điều 5: Hạn Mức Tạm Ứng Công Tác Phí\n\n"
        "15.000.000 VNĐ cho mỗi đợt công tác nội địa không quá 5 ngày."
    )
    doc = ParsedDocument(filename="financial_rules.md", file_type="markdown", pages=[ParsedPage(page_number=1, text=raw_doc)])

    chunker = DocumentChunker(child_chunk_size_chars=300, inject_breadcrumbs=True)
    chunks = chunker.chunk_document(doc, doc_id="doc_fin_05")

    target_chunk = next(c for c in chunks if "15.000.000" in c.text)
    # DoD 1: Breadcrumb injected at the very top line
    assert target_chunk.text.startswith("[Ngữ cảnh: ")
    assert "QUY CHẾ TÀI CHÍNH NĂM 2026" in target_chunk.text
    assert "Điều 5: Hạn Mức Tạm Ứng Công Tác Phí" in target_chunk.text

    # Verify query for heading term matches even if the body only has numbers
    assert "Hạn Mức Tạm Ứng" in target_chunk.text

    # DoD 3: Original body text is preserved after the breadcrumb header
    lines = target_chunk.text.split("\n\n")
    assert len(lines) >= 2
    body_content = lines[-1].strip()
    assert "15.000.000 VNĐ cho mỗi đợt công tác nội địa không quá 5 ngày." == body_content


@pytest.mark.anyio
async def test_qdrant_payload_structure_and_filters(monkeypatch):
    """
    ING-RAG-03 DoD 2:
    - Qdrant Payload contains doc_id, chunk_id, parent_id, heading_path, content_type, token_count.
    - Qdrant filter condition builder generates accurate clauses for content_type and heading_path.
    """
    adapter = QdrantVectorStoreAdapter(base_url="http://mock-qdrant:6333", collection_name="test_col")

    # 1. Verify _build_filter_conditions supports content_type and heading_path
    filters = adapter._build_filter_conditions(
        tenant_id="tenant_bank",
        user_role="auditor",
        department="RISK",
        doc_ids=["doc_100"],
        content_type="table",
        heading_path="SOP > Chapter 2 > Table 1",
    )

    keys = [f.get("key") for f in filters if "key" in f]
    assert "content_type" in keys
    assert "heading_path" in keys
    assert "department" in keys
    assert "doc_id" in keys

    c_type_filter = next(f for f in filters if f.get("key") == "content_type")
    assert c_type_filter["match"]["value"] == "table"

    h_path_filter = next(f for f in filters if f.get("key") == "heading_path")
    assert h_path_filter["match"]["value"] == "SOP > Chapter 2 > Table 1"

    # 2. Verify payload construction during upsert_chunks
    chunk = DocumentChunk(
        chunk_id="chunk_100_0",
        doc_id="doc_100",
        chunk_index=0,
        page_number=1,
        text="[Ngữ cảnh: SOP > Finance]\n\nSố dư khả dụng tối thiểu là 500 triệu VNĐ.",
        metadata={
            "chunk_id": "chunk_100_0",
            "parent_id": "parent_doc_100_p1",
            "heading_path": "SOP > Finance",
            "heading": "Finance",
            "content_type": "text",
            "strategy": "hierarchical_structural",
            "char_length": 65,
            "token_count": 16,
            "source_page": 1,
        },
    )

    captured_points = []

    class MockResponse:
        status_code = 200
        def raise_for_status(self):
            pass
        def json(self):
            return {"result": {}}

    async def mock_put(url, json=None):
        if "points" in url:
            captured_points.extend(json["points"])
        return MockResponse()

    monkeypatch.setattr(adapter, "ensure_collection", lambda: asyncio.sleep(0))
    monkeypatch.setattr(httpx.AsyncClient, "put", lambda self, url, json=None: mock_put(url, json=json))

    await adapter.upsert_chunks(
        chunks=[chunk],
        vectors=[[0.01] * 1024],
        tenant_id="tenant_bank",
        title="Quy trình Quản lý Rủi ro",
        filename="Risk_Management_SOP.docx",
        file_type="docx",
        department="RISK",
        allowed_roles=["*"],
    )

    assert len(captured_points) == 1
    payload = captured_points[0]["payload"]

    # Verify all ING-RAG-03 required fields in Qdrant Payload
    assert payload["doc_id"] == "doc_100"
    assert payload["chunk_id"] == "chunk_100_0"
    assert payload["parent_id"] == "parent_doc_100_p1"
    assert payload["heading_path"] == "SOP > Finance"
    assert payload["content_type"] == "text"
    assert payload["token_count"] == 16
    assert payload["char_length"] == 65
    assert payload["tenant_id"] == "tenant_bank"
    assert payload["title"] == "Quy trình Quản lý Rủi ro"
    assert payload["filename"] == "Risk_Management_SOP.docx"
    assert payload["file_type"] == "docx"
