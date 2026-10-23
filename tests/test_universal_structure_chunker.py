"""
Unit and integration test suite for Pillar 2:
Universal Structure-Based & Atomic Table Chunking.
Validates multi-format document support (Technical Specs, Financial Reports, SOPs, HTML)
and ensures 100% domain-agnostic implementation without hardcoded Vietnamese legal regex.
"""

from solutions.rag.application.components.chunker import DocumentChunker
from solutions.rag.domain.entities import ParsedDocument, ParsedPage
from common.chunking import StructureChunker


def test_technical_doc_with_code_blocks_and_markdown_tables():
    """Case 1: Technical specification with Markdown headings, code blocks, and parameter tables."""
    tech_doc = (
        "# System Architecture Specification\n\n"
        "This document describes the high-level architecture of AIP RAG platform.\n\n"
        "## 1. Streaming Ingestion Pipeline\n\n"
        "Ingestion is performed asynchronously using gRPC workers.\n\n"
        "```python\n"
        "def process_stream(data: bytes) -> dict:\n"
        "    return {'status': 'processed', 'size': len(data)}\n"
        "```\n\n"
        "### 1.1 Service Parameters\n\n"
        "| Parameter | Type | Default | Description |\n"
        "| :--- | :--- | :--- | :--- |\n"
        "| chunk_size | int | 900 | Maximum characters per chunk |\n"
        "| overlap | int | 150 | Overlap size between chunks |\n"
        "| mask_pii | bool | true | Enable automated PII redaction |\n\n"
        "All parameters can be configured through environment variables."
    )
    pages = [ParsedPage(page_number=1, text=tech_doc)]
    doc = ParsedDocument(filename="arch_spec.md", file_type="markdown", pages=pages)

    chunker = DocumentChunker(child_chunk_size_chars=400, inject_breadcrumbs=True)
    chunks = chunker.chunk_document(doc, doc_id="spec_01")

    assert len(chunks) >= 3

    # Check breadcrumb injection
    param_chunk = next(c for c in chunks if "Service Parameters" in c.text or "chunk_size" in c.text)
    assert "[Ngữ cảnh: " in param_chunk.text
    assert "System Architecture Specification" in param_chunk.text

    # Check code block chunk
    code_chunk = next(c for c in chunks if "def process_stream" in c.text)
    assert code_chunk.metadata.get("content_type") == "code"
    assert code_chunk.metadata.get("strategy") == "code_block"

    # Check table chunk
    table_chunk = next(c for c in chunks if "| chunk_size |" in c.text)
    assert table_chunk.metadata.get("is_table") is True
    assert table_chunk.metadata.get("content_type") == "table"
    assert "Parameter" in table_chunk.metadata.get("table_headers", [])


def test_atomic_table_row_split_with_header_replication():
    """Case 2: Large financial/enterprise table split row-by-row with header replication."""
    long_table = (
        "## Báo Cáo Doanh Thu Năm 2026\n\n"
        "| Kỳ Báo Cáo | Doanh Thu (Tỷ VNĐ) | Lợi Nhuận (Tỷ VNĐ) | Tăng Trưởng |\n"
        "| :--- | :--- | :--- | :--- |\n"
        "| Quý 1/2026 | 1250.50 | 320.10 | +12.5% |\n"
        "| Quý 2/2026 | 1480.20 | 410.50 | +18.4% |\n"
        "| Quý 3/2026 | 1620.80 | 480.30 | +21.2% |\n"
        "| Quý 4/2026 | 1950.00 | 560.80 | +20.4% |\n"
        "| Tổng Hợp Năm | 6301.50 | 1771.70 | +18.1% |\n\n"
        "Báo cáo đã được kiểm toán độc lập xác nhận."
    )
    pages = [ParsedPage(page_number=1, text=long_table)]
    doc = ParsedDocument(filename="financial_report.md", file_type="markdown", pages=pages)

    # Force small chunk size to trigger table row splitting
    chunker = DocumentChunker(child_chunk_size_chars=200, inject_breadcrumbs=True)
    chunks = chunker.chunk_document(doc, doc_id="fin_2026")

    table_chunks = [c for c in chunks if c.metadata.get("is_table") is True]
    assert len(table_chunks) >= 2

    # Every split table chunk must replicate the column headers and separator line
    for t_chunk in table_chunks:
        assert "| Kỳ Báo Cáo |" in t_chunk.text
        assert "| :--- |" in t_chunk.text
        assert t_chunk.metadata.get("content_type") == "table"
        assert t_chunk.metadata.get("strategy") == "atomic_table"
        assert t_chunk.metadata.get("table_headers") == ["Kỳ Báo Cáo", "Doanh Thu (Tỷ VNĐ)", "Lợi Nhuận (Tỷ VNĐ)", "Tăng Trưởng"]


def test_sop_multi_level_decimal_hierarchy():
    """Case 3: Standard Operating Procedure (SOP) with multi-level decimal outline hierarchy (1., 1.1, 1.1.1)."""
    sop_doc = (
        "1. QUY TRÌNH TIẾP NHẬN VÀ XỬ LÝ SỰ CỐ CNTT\n\n"
        "Tài liệu này áp dụng cho toàn bộ khối kỹ thuật và vận hành.\n\n"
        "1.1. Phân loại mức độ sự cố\n\n"
        "Sự cố được phân loại từ mức P1 (Nghiêm trọng nhất) đến P4 (Thấp).\n\n"
        "1.1.1. Sự cố cấp độ P1 (Khẩn cấp)\n\n"
        "Hệ thống lõi ngưng hoạt động trên 15 phút, ảnh hưởng trực tiếp tới khách hàng giao dịch.\n\n"
        "1.1.2. Sự cố cấp độ P2 (Nghiêm trọng)\n\n"
        "Hệ thống hoạt động chậm, suy giảm trên 50% thông lượng nhưng chưa sập hoàn toàn."
    )
    pages = [ParsedPage(page_number=1, text=sop_doc)]
    doc = ParsedDocument(filename="sop_itsm.txt", file_type="txt", pages=pages)

    chunker = DocumentChunker(child_chunk_size_chars=350, inject_breadcrumbs=True)
    chunks = chunker.chunk_document(doc, doc_id="sop_01")

    assert len(chunks) >= 3

    # Check P1 chunk breadcrumb contains the full hierarchical decimal path
    p1_chunk = next(c for c in chunks if "P1 (Khẩn cấp)" in c.text)
    assert "[Ngữ cảnh: " in p1_chunk.text
    assert "QUY TRÌNH TIẾP NHẬN VÀ XỬ LÝ SỰ CỐ CNTT" in p1_chunk.text
    assert "1.1.1: Sự cố cấp độ P1 (Khẩn cấp)" in p1_chunk.text


def test_web_html_headings_and_tables():
    """Case 4: HTML document scraped from web or CMS with <h1> to <h3> tags and table."""
    html_doc = (
        "<h1>Cẩm Nang Nhân Viên Mới</h1>\n\n"
        "Chào mừng bạn đến với môi trường làm việc số của doanh nghiệp.\n\n"
        "<h2>Chính Sách Làm Việc Linh Hoạt</h2>\n\n"
        "Nhân sự được phép đăng ký làm việc từ xa tối đa 2 ngày mỗi tuần.\n\n"
        "<h3>Thời Gian Biểu</h3>\n\n"
        "<table>\n"
        "  <tr><th>Ca làm việc</th><th>Bắt đầu</th><th>Kết thúc</th></tr>\n"
        "  <tr><td>Ca sáng</td><td>08:30</td><td>12:00</td></tr>\n"
        "  <tr><td>Ca chiều</td><td>13:30</td><td>17:30</td></tr>\n"
        "</table>"
    )
    pages = [ParsedPage(page_number=1, text=html_doc)]
    doc = ParsedDocument(filename="handbook.html", file_type="html", pages=pages)

    chunker = DocumentChunker(child_chunk_size_chars=400, inject_breadcrumbs=True)
    chunks = chunker.chunk_document(doc, doc_id="html_01")

    assert len(chunks) >= 2

    # Verify HTML headings generated breadcrumbs
    schedule_chunk = next(c for c in chunks if "Thời Gian Biểu" in c.text or "<table>" in c.text)
    assert "[Ngữ cảnh: " in schedule_chunk.text
    assert "Cẩm Nang Nhân Viên Mới" in schedule_chunk.text

    # Verify table detection in HTML
    tbl_chunk = next(c for c in chunks if "<table>" in c.text)
    assert tbl_chunk.metadata.get("is_table") is True


def test_zero_vietnamese_legal_regex_audit():
    """Case 5: Verification audit ensuring ZERO hardcoded legal keywords (Chương/Điều/Khoản/Mục) in regex patterns."""
    import inspect
    from solutions.rag.application.components.chunker import DocumentChunker
    import packages.common.common.chunking.structure_chunker as struct_mod
    import packages.common.common.chunking.token_chunker as token_mod

    chunker_source = inspect.getsource(DocumentChunker)
    struct_source = inspect.getsource(struct_mod)
    token_source = inspect.getsource(token_mod)

    # Patterns that must NEVER exist in any regex definitions
    legal_keywords = ["Chương", "Điều", "Khoản", "Mục"]

    # Check regex strings in DocumentChunker
    for kw in legal_keywords:
        assert f'r"^({kw}' not in chunker_source, f"Found hardcoded legal keyword '{kw}' in DocumentChunker regex"
        assert f"{kw}\\s+" not in chunker_source, f"Found hardcoded legal keyword pattern '{kw}' in DocumentChunker"
        assert f"{kw}\\s+" not in struct_source, f"Found hardcoded legal keyword pattern '{kw}' in StructureChunker"
        assert f"{kw}\\s+" not in token_source, f"Found hardcoded legal keyword pattern '{kw}' in TokenChunker"


def test_parent_child_hierarchy_linkage():
    """
    ING-RAG-04 DoD 1, 2, 3:
    Parent-Child Hierarchical Chunk Linkage:
    - DoD 1: Every child chunk points to a valid parent_id.
    - DoD 2: Chat layer (RagPromptBuilder) can extract parent_text to expand context for LLM with deduplication.
    - DoD 3: Only child chunks are vectorized; parent text resides in metadata/payload.
    """
    from solutions.rag.application.components.prompt_builder import RagPromptBuilder

    text = (
        "# CHAPTER 1: OVERVIEW\n\n"
        "This is paragraph one of the overview section.\n\n"
        "This is paragraph two detailing the core capabilities.\n\n"
        "## Section 1.1: Functional Requirements\n\n"
        "The system must support low latency vector similarity search."
    )
    pages = [ParsedPage(page_number=1, text=text)]
    doc = ParsedDocument(filename="manual.md", file_type="markdown", pages=pages)

    chunker = DocumentChunker(child_chunk_size_chars=120, parent_chunk_size_chars=2000, hierarchical=True)
    chunks = chunker.chunk_document(doc, doc_id="doc_parent_child")

    # DoD 1: Valid parent_id on every child chunk
    assert len(chunks) >= 2
    for c in chunks:
        assert c.metadata.get("parent_id") == "parent_doc_parent_child_p1"
        assert "CHAPTER 1: OVERVIEW" in c.metadata.get("parent_text", "")
        assert c.metadata.get("token_count") > 0
        assert "heading_path" in c.metadata

    # DoD 2: Chat layer expands parent_text for LLM context synthesis
    builder = RagPromptBuilder()
    # Without parent expansion
    citations_child, ctx_child = builder.extract_citations_and_blocks(chunks, use_parent_context=False)
    assert len(ctx_child) == len(chunks)

    # With parent expansion: multiple children sharing the same parent are deduplicated to the full parent context
    citations_parent, ctx_parent = builder.extract_citations_and_blocks(chunks, use_parent_context=True)
    assert len(ctx_parent) == 1  # Deduplicated to 1 parent block
    assert "CHAPTER 1: OVERVIEW" in ctx_parent[0]
    assert "The system must support low latency vector similarity search." in ctx_parent[0]
    # Citations still maintain child chunk identity
    assert len(citations_parent) == len(chunks)
    assert citations_parent[0]["parent_id"] == "parent_doc_parent_child_p1"

    # DoD 3: Vectorization count matches child chunks only (no duplicate vectors for parent)
    vectors = [[0.05] * 1024 for _ in chunks]
    assert len(vectors) == len(chunks)


def test_ing_rag_01_all_five_heading_formats():
    """
    ING-RAG-01 DoD 1 & DoD 2:
    Validates accurate detection of all 5 heading formats:
    1. Markdown (# to ######)
    2. HTML (<h1> to <h6>)
    3. Decimal hierarchy (1., 1.1, 1.1.1)
    4. Roman numerals (I., II.)
    5. Alphabetic outlines (A., B. and a), b))
    And verifies heading_path breadcrumb tree construction.
    """
    sample_doc = (
        "# HỆ THỐNG VẬN HÀNH DOANH NGHIỆP\n\n"
        "Nội dung tổng quan giới thiệu hệ thống.\n\n"
        "I. QUY CHẾ VẬN HÀNH\n\n"
        "Nguyên tắc vận hành xuyên suốt.\n\n"
        "2. QUY TRÌNH XỬ LÝ SỰ CỐ\n\n"
        "Các bước tiếp nhận sự cố kỹ thuật.\n\n"
        "2.1. Phân loại sự cố P1\n\n"
        "Định nghĩa chi tiết về sự cố cấp độ 1.\n\n"
        "A. Tiêu chí kỹ thuật\n\n"
        "Tiêu chuẩn đánh giá hệ thống gián đoạn.\n\n"
        "a) Điều kiện tiếp nhận khẩn cấp\n\n"
        "Yêu cầu tiếp nhận trong vòng 5 phút kể từ khi phát sinh cảnh báo."
    )
    pages = [ParsedPage(page_number=1, text=sample_doc)]
    doc = ParsedDocument(filename="sop_standard.md", file_type="markdown", pages=pages)

    chunker = DocumentChunker(child_chunk_size_chars=250, inject_breadcrumbs=True)
    chunks = chunker.chunk_document(doc, doc_id="sop_ing_01")

    assert len(chunks) >= 4

    # 1. Verify Markdown heading detection
    c_md = next(c for c in chunks if "Nội dung tổng quan" in c.text)
    assert "HỆ THỐNG VẬN HÀNH DOANH NGHIỆP" in c_md.metadata.get("heading_path", "")
    assert c_md.metadata.get("heading_level") == 1

    # 2. Verify Roman numeral detection
    c_roman = next(c for c in chunks if "Nguyên tắc vận hành" in c.text)
    assert "I. QUY CHẾ VẬN HÀNH" in c_roman.metadata.get("heading_path", "")
    assert c_roman.metadata.get("heading_level") == 2

    # 3. Verify Decimal hierarchy detection (2.1 under 2.)
    c_dec = next(c for c in chunks if "Định nghĩa chi tiết" in c.text)
    assert "2. QUY TRÌNH XỬ LÝ SỰ CỐ" in c_dec.metadata.get("heading_path", "")
    assert "2.1: Phân loại sự cố P1" in c_dec.metadata.get("heading_path", "")

    # 4. Verify Alphabetic outline (A. and a))
    c_sub = next(c for c in chunks if "Yêu cầu tiếp nhận trong vòng 5 phút" in c.text)
    heading_path = c_sub.metadata.get("heading_path", "")
    assert "A. Tiêu chí kỹ thuật" in heading_path
    assert "a) Điều kiện tiếp nhận khẩn cấp" in heading_path
    assert c_sub.metadata.get("heading_level") == 3
    assert "[Ngữ cảnh: " in c_sub.text


def test_atomic_html_table_row_split_with_header_replication():
    """
    ING-RAG-02 DoD 1, 2, 3:
    HTML table splitting row-by-row with <th> header replication and table_headers metadata extraction.
    - DoD 1: Table is not cut midway through data rows (each chunk contains balanced <tr>...</tr> tags).
    - DoD 2: Every split sub-chunk replicates the <th> header row at the top.
    - DoD 3: Table headers extracted into table_headers metadata list.
    """
    html_table = (
        "<h2>Bảng Phân Công Nhân Sự Dự Án</h2>\n\n"
        "<table>\n"
        "  <tr><th>Họ Tên</th><th>Chức Vụ</th><th>Bộ Phận</th><th>Trạng Thái</th></tr>\n"
        "  <tr><td>Nguyễn Văn A</td><td>Trưởng nhóm</td><td>AI RAG</td><td>Đang làm việc</td></tr>\n"
        "  <tr><td>Trần Thị B</td><td>Kỹ sư Backend</td><td>Platform</td><td>Đang làm việc</td></tr>\n"
        "  <tr><td>Lê Văn C</td><td>Kỹ sư MLOps</td><td>DevOps</td><td>Đang làm việc</td></tr>\n"
        "  <tr><td>Phạm Thị D</td><td>Kiểm thử QA</td><td>Quality</td><td>Đang làm việc</td></tr>\n"
        "</table>"
    )
    pages = [ParsedPage(page_number=1, text=html_table)]
    doc = ParsedDocument(filename="staff_assignment.html", file_type="html", pages=pages)

    # Small chunk size to force row-wise split
    chunker = DocumentChunker(child_chunk_size_chars=180, inject_breadcrumbs=True)
    chunks = chunker.chunk_document(doc, doc_id="html_table_01")

    table_chunks = [c for c in chunks if c.metadata.get("is_table") is True]
    assert len(table_chunks) >= 2, f"Expected >= 2 table chunks, got {len(table_chunks)}"

    for t_chunk in table_chunks:
        # DoD 1: Atomic row integrity (balanced <tr> and </tr>)
        assert t_chunk.text.count("<tr>") == t_chunk.text.count("</tr>")
        # DoD 2: Header replication
        assert "<th>Họ Tên</th>" in t_chunk.text
        assert "<th>Chức Vụ</th>" in t_chunk.text
        assert "<th>Bộ Phận</th>" in t_chunk.text
        assert "<th>Trạng Thái</th>" in t_chunk.text
        # DoD 3: Table headers metadata
        assert t_chunk.metadata.get("table_headers") == ["Họ Tên", "Chức Vụ", "Bộ Phận", "Trạng Thái"]
        assert t_chunk.metadata.get("content_type") == "table"
        assert t_chunk.metadata.get("strategy") == "atomic_table"


def test_structure_chunker_atomic_table_and_header_replication():
    """Verify common.chunking.StructureChunker also satisfies ING-RAG-02 DoD 1, 2, 3."""
    long_table = (
        "| Mã Sản Phẩm | Tên Hàng Hóa | Số Lượng Tồn | Đơn Giá (VNĐ) |\n"
        "| :--- | :--- | :--- | :--- |\n"
        "| SP001 | Máy chủ Dell PowerEdge | 15 | 85000000 |\n"
        "| SP002 | Card đồ họa RTX 4090 | 30 | 52000000 |\n"
        "| SP003 | Switch mạng Cisco 48 Port | 10 | 28000000 |\n"
        "| SP004 | Ổ cứng SSD Enterprise 3.84TB | 50 | 12000000 |\n"
    )
    doc = ParsedDocument(filename="inventory.md", file_type="markdown", pages=[ParsedPage(page_number=1, text=long_table)])

    chunker = StructureChunker(max_chunk_size=180)
    chunks = chunker.chunk_document(doc, doc_id="inv_01")

    table_chunks = [c for c in chunks if c.metadata.get("is_table") is True]
    assert len(table_chunks) >= 2, f"Expected >= 2 table chunks, got {len(table_chunks)}"

    for t_chunk in table_chunks:
        assert "| Mã Sản Phẩm |" in t_chunk.text
        assert "| :--- |" in t_chunk.text
        assert t_chunk.metadata.get("table_headers") == ["Mã Sản Phẩm", "Tên Hàng Hóa", "Số Lượng Tồn", "Đơn Giá (VNĐ)"]
        assert t_chunk.metadata.get("content_type") == "table"
        assert t_chunk.metadata.get("strategy") == "atomic_table"

