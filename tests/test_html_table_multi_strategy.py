from solutions.rag.domain.entities import ParsedDocument, ParsedPage
from solutions.rag.application.components.chunker import DocumentChunker

def test_html_table_multi_strategy_thead_and_caption():
    """
    Test Multi-Strategy HTML Table Chunking:
    1. Preserves table attributes (class, id, style).
    2. Preserves <caption> and replicates across split sub-chunks.
    3. Preserves multi-row <thead> with colspan and rowspan.
    4. Sub-chunks are valid HTML tables with thead and tbody.
    """
    html = """
    <table class="financial-table report-v2" id="fin-2026" style="width: 100%;">
      <caption>Báo Cáo Tài Chính Hợp Nhất 2026</caption>
      <thead>
        <tr>
          <th rowspan="2">Hạng Mục</th>
          <th colspan="2">Năm 2025</th>
          <th colspan="2">Năm 2026</th>
        </tr>
        <tr>
          <th>Kế hoạch</th>
          <th>Thực hiện</th>
          <th>Kế hoạch</th>
          <th>Thực hiện</th>
        </tr>
      </thead>
      <tbody>
        <tr><td>Doanh thu bán hàng</td><td>1000</td><td>1050</td><td>1200</td><td>1250</td></tr>
        <tr><td>Giá vốn hàng bán</td><td>600</td><td>620</td><td>700</td><td>720</td></tr>
        <tr><td>Lợi nhuận gộp</td><td>400</td><td>430</td><td>500</td><td>530</td></tr>
        <tr><td>Chi phí bán hàng</td><td>100</td><td>105</td><td>120</td><td>125</td></tr>
        <tr><td>Chi phí quản lý</td><td>80</td><td>82</td><td>95</td><td>98</td></tr>
        <tr><td>Lợi nhuận thuần</td><td>220</td><td>243</td><td>285</td><td>307</td></tr>
      </tbody>
    </table>
    """
    doc = ParsedDocument(filename="fin_report.html", file_type="html", pages=[ParsedPage(page_number=1, text=html)])
    
    # Small chunk size to force row splitting
    chunker = DocumentChunker(child_chunk_size_chars=400, inject_breadcrumbs=True)
    chunks = chunker.chunk_document(doc, doc_id="doc_fin")
    
    table_chunks = [c for c in chunks if c.metadata.get("is_table") is True]
    assert len(table_chunks) >= 2, f"Expected multiple chunks, got {len(table_chunks)}"
    
    for tc in table_chunks:
        # 1. Attributes preserved
        assert 'class="financial-table report-v2"' in tc.text
        assert 'id="fin-2026"' in tc.text
        # 2. Caption preserved
        assert "<caption>Báo Cáo Tài Chính Hợp Nhất 2026</caption>" in tc.text
        # 3. Multi-row thead replicated
        assert "<th>Hạng Mục</th>" in tc.text
        assert 'colspan="2"' in tc.text
        assert "<th>Kế hoạch</th>" in tc.text
        assert "<th>Thực hiện</th>" in tc.text
        # 4. Valid tags
        assert tc.text.count("<thead>") == 1
        assert tc.text.count("</thead>") == 1
        assert tc.text.count("<tbody>") == 1
        assert tc.text.count("</tbody>") == 1
        # 5. Metadata extraction
        headers = tc.metadata.get("table_headers", [])
        assert "Hạng Mục" in headers
        assert "Năm 2025" in headers
        assert "Kế hoạch" in headers

def test_html_table_nested_table_preservation():
    """
    Test that a nested table inside a <td> is NOT destroyed or flattened into the outer rows.
    """
    html = """
    <table class="outer-table">
      <thead>
        <tr><th>Bộ Phận</th><th>Chi Tiết Nhân Lực</th></tr>
      </thead>
      <tbody>
        <tr>
          <td>Phòng Kỹ Thuật</td>
          <td>
            <table class="inner-table">
              <tr><td>Frontend</td><td>10 người</td></tr>
              <tr><td>Backend</td><td>15 người</td></tr>
            </table>
          </td>
        </tr>
        <tr><td>Phòng Kinh Doanh</td><td>25 người</td></tr>
        <tr><td>Phòng Marketing</td><td>12 người</td></tr>
        <tr><td>Phòng Nhân Sự</td><td>6 người</td></tr>
      </tbody>
    </table>
    """
    doc = ParsedDocument(filename="nested.html", file_type="html", pages=[ParsedPage(page_number=1, text=html)])
    chunker = DocumentChunker(child_chunk_size_chars=250, inject_breadcrumbs=True)
    chunks = chunker.chunk_document(doc, doc_id="nested_01")
    
    table_chunks = [c for c in chunks if c.metadata.get("is_table") is True]
    assert len(table_chunks) >= 2
    
    # First chunk should contain the intact nested table inside the <td>
    chunk_with_nested = next(c for c in table_chunks if "Phòng Kỹ Thuật" in c.text)
    assert '<table class="inner-table">' in chunk_with_nested.text
    assert "</table>" in chunk_with_nested.text
    assert "Frontend" in chunk_with_nested.text
    assert "Backend" in chunk_with_nested.text

def test_html_table_non_th_headers():
    """
    Test HTML table exported from legacy CMS or Word that uses <td> instead of <th>,
    styled with class='header' or <strong> tags.
    """
    html = """
    <table border="1">
      <tr class="header-row">
        <td><strong>STT</strong></td>
        <td><strong>Tên Dịch Vụ</strong></td>
        <td><strong>Đơn Giá</strong></td>
      </tr>
      <tr><td>1</td><td>Cài đặt máy chủ</td><td>500,000</td></tr>
      <tr><td>2</td><td>Bảo trì định kỳ</td><td>1,200,000</td></tr>
      <tr><td>3</td><td>Khắc phục sự cố 24/7</td><td>2,000,000</td></tr>
      <tr><td>4</td><td>Kiểm toán an toàn thông tin</td><td>5,000,000</td></tr>
    </table>
    """
    doc = ParsedDocument(filename="legacy.html", file_type="html", pages=[ParsedPage(page_number=1, text=html)])
    chunker = DocumentChunker(child_chunk_size_chars=220, inject_breadcrumbs=True)
    chunks = chunker.chunk_document(doc, doc_id="legacy_01")
    
    table_chunks = [c for c in chunks if c.metadata.get("is_table") is True]
    assert len(table_chunks) >= 2
    
    for tc in table_chunks:
        # Header must be replicated even though it uses <td> and not <th>
        assert "STT" in tc.text
        assert "Tên Dịch Vụ" in tc.text
        assert "Đơn Giá" in tc.text
        headers = tc.metadata.get("table_headers", [])
        assert "STT" in headers
        assert "Tên Dịch Vụ" in headers
        assert "Đơn Giá" in headers
