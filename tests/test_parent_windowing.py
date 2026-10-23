"""
Unit tests for Audit Item 5: Parent Context Windowing and Chunker Architecture hardening.
Verifies:
1. Snippet location with breadcrumbs / metadata prefixes.
2. Snippet location with overlap text / repeated phrases across paragraphs.
3. Stable parent window deduplication across boundaries.
4. Fallback behavior when snippet cannot be matched (cursor hint vs top-of-page).
5. Schema consistency through unified _create_chunk.
"""

import logging
from solutions.rag.application.components.chunker import DocumentChunker
from solutions.rag.domain.entities import ParsedDocument, ParsedPage


def test_snippet_location_with_breadcrumbs():
    """Verify that breadcrumb prefixes do not break snippet location."""
    chunker = DocumentChunker(child_chunk_size_chars=300, parent_chunk_size_chars=1000)
    page_text = (
        "Giới thiệu chung về công ty. " * 10
        + "\n\nQuy trình bảo mật thông tin nội bộ yêu cầu toàn bộ nhân viên phải đổi mật khẩu định kỳ 90 ngày một lần. "
        + "Mọi hành vi vi phạm sẽ bị xử lý kỷ luật nghiêm khắc."
        + "\n\n" + "Phụ lục bổ sung các quy định chi tiết. " * 10
    )
    doc = ParsedDocument(
        filename="security_policy.md",
        file_type="markdown",
        pages=[ParsedPage(page_number=1, text=page_text)],
    )

    chunks = chunker.chunk_document(doc, doc_id="sec_01", title="Chính Sách Bảo Mật")
    assert len(chunks) > 1

    # Find chunk containing security policy
    target_chunk = next(c for c in chunks if "đổi mật khẩu định kỳ" in c.text)
    assert target_chunk.metadata.get("parent_id") is not None
    # Parent text must contain the child text
    assert "đổi mật khẩu định kỳ" in target_chunk.metadata["parent_text"]
    # Child chunk has enriched breadcrumbs/title
    assert "[Ngữ cảnh: Chính Sách Bảo Mật]" in target_chunk.text


def test_repeated_overlap_text_forward_search():
    """Verify that overlap text between sub-paragraphs does not erroneously snap to earlier matches."""
    chunker = DocumentChunker(child_chunk_size_chars=250, child_overlap_chars=50, parent_chunk_size_chars=1000)
    
    repeated_phrase = "Điều khoản quan trọng cần tuân thủ nghiêm ngặt trong doanh nghiệp. "
    # Create large paragraph where repeated_phrase appears early and late
    large_paragraph = (
        repeated_phrase * 3
        + "Nội dung phần đầu của văn bản hướng dẫn xử lý hợp đồng. " * 3
        + repeated_phrase * 2
        + "Nội dung phần cuối của văn bản hướng dẫn thanh lý tài sản. " * 3
    )

    doc = ParsedDocument(
        filename="contract_guide.txt",
        file_type="text",
        pages=[ParsedPage(page_number=1, text=large_paragraph)],
    )

    chunks = chunker.chunk_document(doc, doc_id="guide_01")
    assert len(chunks) >= 3

    # The last chunk should have its parent_text centered around the end, containing "thanh lý tài sản"
    last_chunk = chunks[-1]
    assert "thanh lý tài sản" in last_chunk.text
    assert "thanh lý tài sản" in last_chunk.metadata["parent_text"]


def test_stable_parent_deduplication_near_boundaries():
    """Verify that adjacent chunks in the same region map to the identical parent window."""
    chunker = DocumentChunker(child_chunk_size_chars=400, parent_chunk_size_chars=2000)

    # 4000-char document
    text = (
        "Đoạn văn mở đầu số 1 về quy trình kỹ thuật. " * 20  # ~900 chars
        + "\n\n"
        + "Đoạn văn tiếp nối số 2 về quy trình kỹ thuật. " * 20  # ~900 chars
        + "\n\n"
        + "Đoạn văn chi tiết số 3 về quy trình triển khai. " * 20 # ~900 chars
        + "\n\n"
        + "Đoạn văn kết luận số 4 về quy trình nghiệm thu. " * 20 # ~900 chars
    )

    doc = ParsedDocument(
        filename="sop.md",
        file_type="markdown",
        pages=[ParsedPage(page_number=1, text=text)],
    )

    chunks = chunker.chunk_document(doc, doc_id="sop_01")
    assert len(chunks) >= 4

    # Chunk 0 and Chunk 1 are both near the first half of the document
    # Under deterministic parent windows, they should share the exact same parent_id and parent_text
    p0_id = chunks[0].metadata["parent_id"]
    p1_id = chunks[1].metadata["parent_id"]
    assert p0_id == p1_id
    assert chunks[0].metadata["parent_text"] == chunks[1].metadata["parent_text"]


def test_locate_snippet_fallback_with_warning(caplog):
    """Verify that when snippet cannot be found, a warning is logged and center is cursor-guided."""
    chunker = DocumentChunker(parent_chunk_size_chars=1000)
    full_text = "Nội dung trang tài liệu dài từ đầu đến cuối trang... " * 100

    with caplog.at_level(logging.WARNING):
        p_id, p_text = chunker._extract_parent_context(
            snippet="Đây là đoạn text hoàn toàn không tồn tại trong trang",
            full_text=full_text,
            doc_id="doc_x",
            page_number=1,
            start_hint=2500,
        )

    # Must log warning
    assert any("Parent window location warning" in r.message for r in caplog.records)
    # Must return valid parent id and text
    assert p_id.startswith("parent_doc_x_p1")
    assert len(p_text) > 0


def test_unified_create_chunk_consistency():
    """Verify _create_chunk creates consistent metadata schema across text, tables, and code."""
    chunker = DocumentChunker()
    page_text = "Dòng 1\nDòng 2\nDòng 3"

    # Text chunk
    c_text, next_cursor = chunker._create_chunk(
        raw_text="Dòng 1",
        clean_page_text=page_text,
        doc_id="d1",
        page_number=1,
        chunk_index=0,
        breadcrumb=["Mục 1"],
        doc_title="Doc Test",
    )
    assert c_text.metadata["content_type"] == "text"
    assert c_text.metadata["strategy"] == "hierarchical_structural"
    assert c_text.metadata["title"] == "Doc Test"
    assert c_text.metadata["heading_path"] == "Mục 1"
    assert next_cursor >= len("Dòng 1")

    # Table chunk
    c_table, _ = chunker._create_chunk(
        raw_text="| A | B |\n|---|---|\n| 1 | 2 |",
        clean_page_text=page_text,
        doc_id="d1",
        page_number=1,
        chunk_index=1,
        breadcrumb=["Mục 2"],
        doc_title="Doc Test",
        content_type="table",
        strategy="atomic_table",
        is_table=True,
        table_headers=["A", "B"],
    )
    assert c_table.metadata["is_table"] is True
    assert c_table.metadata["content_type"] == "table"
    assert c_table.metadata["strategy"] == "atomic_table"
    assert c_table.metadata["table_headers"] == ["A", "B"]
    assert c_table.metadata["title"] == "Doc Test"

    # Code chunk
    c_code, _ = chunker._create_chunk(
        raw_text="def foo(): pass",
        clean_page_text=page_text,
        doc_id="d1",
        page_number=1,
        chunk_index=2,
        breadcrumb=["Mục 3"],
        doc_title="Doc Test",
        content_type="code",
        strategy="code_block",
    )
    assert c_code.metadata["content_type"] == "code"
    assert c_code.metadata["strategy"] == "code_block"
    assert c_code.metadata["title"] == "Doc Test"
