"""
Unit test suite for Enterprise RAG Chunking Strategies.
Verifies compliance with RAG Architectures:
- Recursive Chunking (Slide pages 22-24)
- Semantic Chunking (Slide pages 25-29)
- Structure-based Chunking (Slide pages 30-33)
- Hybrid Production Chunker & PII Sanitization
"""

from common.chunking import (
    ChunkerFactory,
    RecursiveChunker,
    SemanticChunker,
    StructureChunker,
    TextChunker,
    TokenChunker,
)


def test_recursive_chunker_hierarchical_split():
    """Verify recursive hierarchy: splits on paragraphs, then sentences, retaining meaning."""
    text = (
        "Đoạn văn 1: Trí tuệ nhân tạo đang thay đổi thế giới một cách mạnh mẽ.\n\n"
        "Đoạn văn 2: Học máy là một tập con của trí tuệ nhân tạo. Nó cho phép hệ thống tự học từ dữ liệu mà không cần lập trình rõ ràng.\n\n"
        "Đoạn văn 3: Xử lý ngôn ngữ tự nhiên giúp máy tính thấu hiểu tiếng Việt."
    )
    chunker = RecursiveChunker(chunk_size=120, chunk_overlap=30, min_chunk_length=20)
    chunks = chunker.split_text(text)

    assert len(chunks) >= 3
    for c in chunks:
        assert len(c["text"]) <= 140
        # Ensure words are not sliced in the middle
        assert not c["text"].endswith("...")


def test_structure_chunker_breadcrumbs_and_tables():
    """Verify Heading hierarchy extraction, breadcrumb context injection, and atomic table preservation."""
    structured_doc = (
        "# CHƯƠNG I: QUY ĐỊNH CHUNG\n\n"
        "Điều 1. Phạm vi điều chỉnh và đối tượng áp dụng cho toàn bộ cán bộ nhân viên công ty.\n\n"
        "| Mã Phòng | Tên Phòng | Trưởng Phòng |\n"
        "| :--- | :--- | :--- |\n"
        "| IT01 | Khối Công Nghệ | Nguyễn Văn A |\n"
        "| HR02 | Khối Nhân Sự | Trần Thị B |\n\n"
        "Điều 2. Nguyên tắc làm việc và kỷ luật nội bộ được phổ biến hàng quý."
    )
    chunker = StructureChunker(max_chunk_size=300, min_chunk_size=30, inject_context_header=True)
    chunks = chunker.split_text(structured_doc)

    assert len(chunks) >= 3

    # Check breadcrumb injection
    d1_chunk = next(c for c in chunks if "Điều 1" in c["text"])
    assert "[Mục: CHƯƠNG I" in d1_chunk["text"]

    # Check table is preserved atomically
    table_chunk = next(c for c in chunks if "| Mã Phòng |" in c["text"])
    assert "| IT01 | Khối Công Nghệ |" in table_chunk["text"]
    assert "| HR02 | Khối Nhân Sự |" in table_chunk["text"]


def test_semantic_chunker_sentence_window():
    """Verify semantic sentence-window chunking never breaks sentences in half."""
    text = (
        "Thủ tướng Chính phủ đã phê duyệt đề án phát triển nguồn nhân lực chất lượng cao. "
        "Dự án này có tổng vốn đầu tư là 2 triệu USD nhằm nâng cao chất lượng giáo dục. "
        "Ngoài ra, các tỉnh vùng biên giới như Huaphan và Champasak cũng được hỗ trợ xây trường học mới. "
        "Đây là biểu tượng cho tình hữu nghị sâu sắc giữa hai quốc gia."
    )
    chunker = SemanticChunker(max_chunk_chars=180, min_chunk_chars=40, sentence_overlap_count=1)
    chunks = chunker.split_text(text)

    assert len(chunks) >= 2
    for c in chunks:
        # Each chunk must end with a sentence terminator
        assert c["text"].rstrip()[-1] in (".", "!", "?", "…")


def test_hybrid_token_chunker_production():
    """Verify production Hybrid Chunker handles tables, headings, and PII masking simultaneously."""
    raw_doc = (
        "## QUY ĐỊNH VỀ BẢO MẬT DỮ LIỆU\n\n"
        "Nhân viên cần bảo vệ số CCCD 038099012345 và email admin@aip.com của khách hàng.\n\n"
        "| Dịch vụ | Port | Giao thức |\n"
        "| :--- | :--- | :--- |\n"
        "| vLLM | 8001 | HTTP/gRPC |\n"
        "| Qdrant | 6333 | HTTP |\n\n"
        "Mọi hành vi vi phạm sẽ bị xử lý kỷ luật theo quy chế của công ty."
    )
    chunker = TokenChunker(chunk_size_chars=250, chunk_overlap_chars=40, mask_pii=True)
    chunks = chunker.split_text(raw_doc)

    assert len(chunks) >= 3

    # Check PII masked
    pii_chunk = next(c for c in chunks if "Nhân viên cần bảo vệ" in c["text"])
    assert "038099012345" not in pii_chunk["text"]
    assert "[ID_REDACTED]" in pii_chunk["text"]
    assert "[EMAIL_REDACTED]" in pii_chunk["text"]

    # Check table kept intact
    table_chunk = next(c for c in chunks if "| Dịch vụ |" in c["text"])
    assert "| vLLM | 8001 |" in table_chunk["text"]


def test_chunker_factory():
    """Verify ChunkerFactory instantiates correct strategy."""
    c_hybrid = ChunkerFactory.create("hybrid")
    assert isinstance(c_hybrid, TokenChunker)

    c_rec = ChunkerFactory.create("recursive")
    assert isinstance(c_rec, RecursiveChunker)

    c_struct = ChunkerFactory.create("structure")
    assert isinstance(c_struct, StructureChunker)

    c_sem = ChunkerFactory.create("semantic")
    assert isinstance(c_sem, SemanticChunker)

    c_text = ChunkerFactory.create("text")
    assert isinstance(c_text, TextChunker)


def test_backwards_compatibility_text_chunker():
    """Verify backwards compatibility for TextChunker."""
    chunker = TextChunker(chunk_size_chars=120, chunk_overlap_chars=20)
    sample_text = (
        "Đoạn văn thứ nhất nói về chính sách nghỉ phép của công ty AIP. Nhân viên có 12 ngày phép một năm.\n\n"
        "Đoạn văn thứ hai nói về tiền thưởng lễ Tết. Tiền thưởng được tính dựa trên hiệu suất công việc KPI.\n\n"
        "Đoạn văn thứ ba nói về bảo hiểm y tế cao cấp dành cho nhân sự chính thức."
    )
    chunks = chunker.split_text(sample_text)
    assert len(chunks) >= 3
    assert chunks[0]["chunk_index"] == 0
    assert "chính sách nghỉ phép" in chunks[0]["text"]
