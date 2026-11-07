"""
Data-layer (step 1) regressions, on synthetic fixtures of each problem class found with the data gate:
tables whose header is multi-level / a caption / a form, sheets holding several tables, PDF tables split across
pages by columns or rows, OCR noise and diacritic misreadings, numbered sentences taken for headings and
headings without content disappearing.
"""

import io

import openpyxl

from benchmarks.rag.src.rag_benchmark.data_audit import table_row_issues
from solutions.rag.application.components.chunker import DocumentChunker
from solutions.rag.domain.entities import ParsedDocument, ParsedPage
from solutions.rag.infrastructure.parsers.excel_parser import ExcelDocumentParser
from solutions.rag.infrastructure.parsers.ocr_text import clean_ocr_text, harmonize_diacritics
from solutions.rag.infrastructure.parsers.pdf_parser import stitch_column_pages, stitch_row_pages
from solutions.rag.infrastructure.parsers.table_grid import GridCell as C
from solutions.rag.infrastructure.parsers.table_grid import render_table, split_blocks


def _header(md: str):
    return [h.strip() for h in [ln for ln in md.splitlines() if ln.startswith("|")][0].strip("|").split("|")]


# ---------------------------------------------------------------- tables
def test_two_level_header_gives_every_column_a_full_name():
    grid = [
        [C("STT", 1), C("Nguồn", 2), C("Nhóm", 3), C("Nhóm", 3), C("Nhóm", 3)],
        [C("STT", 1), C("Nguồn", 2), C("A"), C("B"), C("C")],
        [C("1"), C("X"), C(""), C(""), C("1")],
    ]
    md = render_table(grid)
    assert _header(md) == ["STT", "Nguồn", "Nhóm / A", "Nhóm / B", "Nhóm / C"]
    assert "| 1 | X |  |  | 1 |" in md  # the second header row is not a data row
    assert table_row_issues(md) == (1, [])


def test_spanning_title_row_is_a_caption_not_the_header():
    grid = [
        [C("BẢNG 1: TIÊU ĐỀ", 9), C("BẢNG 1: TIÊU ĐỀ", 9), C("BẢNG 1: TIÊU ĐỀ", 9)],
        [C("Mã"), C("Tên"), C("Điểm")],
        [C("M1"), C("Một"), C("10")],
    ]
    md = render_table(grid)
    assert md.startswith("**BẢNG 1: TIÊU ĐỀ**\n\n| Mã | Tên | Điểm |")
    lone = [[C("Danh sách"), C(""), C("")], [C("Mã"), C("Tên"), C("Điểm")], [C("M1"), C("Một"), C("10")]]
    assert render_table(lone).startswith("**Danh sách**")


def test_form_table_is_rendered_as_label_value_lines():
    grid = [[C("Tên: A", 1), C("Tên: A", 1), C("Mã:")], [C("Địa điểm:"), C("Phố 1", 2), C("Phố 1", 2)]]
    md = render_table(grid)
    assert "|" not in md and "Tên: A; Mã:" in md and "Địa điểm:; Phố 1" in md


def test_sheet_with_two_tables_is_split_at_the_caption_after_an_empty_row():
    rows = [
        [C("BẢNG 1", 1), C("BẢNG 1", 1)], [C("Mã"), C("Điểm")], [C("A"), C("1")],
        [C(""), C("")],
        [C("BẢNG 2", 2), C("BẢNG 2", 2)], [C("Mã"), C("Mức")], [C("B"), C("2")],
    ]
    blocks = split_blocks(rows)
    assert len(blocks) == 2 and _header(render_table(blocks[1])) == ["Mã", "Mức"]


def test_excel_tables_keep_their_header_in_every_chunk():
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["BẢNG 1: TIÊU CHÍ", None, None])
    ws.merge_cells("A1:C1")
    ws.append(["Mã", "Nội dung", "Điểm tối đa"])
    for i in range(40):
        ws.append([f"T{i:02d}", "nội dung dài " * 12, 5])
    buf = io.BytesIO()
    wb.save(buf)
    parsed = ExcelDocumentParser().parse(buf.getvalue(), "x.xlsx")
    chunks = DocumentChunker(child_chunk_size_chars=600, child_overlap_chars=50, parent_chunk_size_chars=2000,
                             hierarchical=True).chunk_document(parsed, "d", title="x")
    table_chunks = [c.text for c in chunks if "| T" in c.text]
    assert len(table_chunks) > 1
    for text in table_chunks:
        rows, problems = table_row_issues(text)
        assert rows and not problems
        assert "Điểm tối đa" in text


# ---------------------------------------------------------------- PDF tables across pages
def _t(page, first_col, tops, y0=50.0, y1=700.0, width=2):
    grid = [[C(v)] + [C(f"{v}-{k}") for k in range(1, width)] for v in first_col]
    return {"page": page, "last_page": page, "grid": grid, "merged_into": None, "tops": tops,
            "y0": y0, "y1": y1, "height": 792.0, "chars": 1}


def test_columns_printed_on_a_later_page_are_joined_to_their_rows():
    a = _t(1, ["Mã", "A1", "A2"], [50, 80, 110])
    b = _t(3, ["Điểm", "10", "5"], [50.5, 80.4, 110.2])
    other = _t(4, ["Mã", "A1", "A2"], [50, 80, 110])  # same rows repeated, not a continuation
    tables = [a, b, other]
    stitch_column_pages(tables)
    assert b["merged_into"] == 1 and other["merged_into"] is None
    assert [c.text for c in a["grid"][1]] == ["A1", "A1-1", "10", "10-1"]


def test_rows_continued_on_the_next_page_are_appended_without_repeated_header():
    a = _t(1, ["Mã", "A1"], [500, 530], y0=500, y1=760)
    b = _t(2, ["Mã", "A2"], [40, 70], y0=40, y1=200)  # header repeated at the top of the next page
    a["grid"][0] = b["grid"][0] = [C("Mã"), C("Điểm")]
    tables = [a, b]
    stitch_row_pages(tables)
    assert b["merged_into"] == 1 and [r[0].text for r in a["grid"]] == ["Mã", "A1", "A2"]


# ---------------------------------------------------------------- OCR text
def test_ocr_border_marks_are_dropped_and_pipes_never_form_a_table():
    text = clean_ocr_text("|\nĐiều 1. Phạm vi |\n_\nA | B")
    assert text == "Điều 1. Phạm vi\nA \\| B"


def test_rare_spelling_of_a_frequent_word_pair_takes_the_dominant_spelling():
    texts = ["xếp loại " * 9 + "rồi xêp loại cuối", "Xêp loại đầu dòng"]  # 9 vs 2: dominant ≥ 4x
    fixed = harmonize_diacritics(texts)
    assert "xêp" not in fixed[0] and fixed[1].startswith("Xếp loại")
    # A misreading made everywhere has no dominant correct spelling in the document: left as is.
    assert harmonize_diacritics(["chỉ cục một, chỉ cục hai"]) == ["chỉ cục một, chỉ cục hai"]


# ---------------------------------------------------------------- chunker headings
def _chunks(text: str):
    doc = ParsedDocument(filename="x.docx", file_type="docx", pages=[ParsedPage(page_number=1, text=text)])
    return [c.text for c in DocumentChunker(hierarchical=True).chunk_document(doc, "d", title="x")]


def test_numbered_sentence_of_running_text_stays_content():
    sentence = ("7.3. Trong kỳ người phụ trách nhập văn bản cộng hoặc trừ điểm theo bằng chứng phát sinh trong tháng "
                "và cơ sở minh chứng cho nội dung cộng trừ điểm của từng người")
    body = "\n\n".join(c.split("]\n\n", 1)[-1] for c in _chunks(f"7. Mục bảy\n\n{sentence}\n\nĐoạn sau."))
    assert sentence in body


def test_heading_without_content_is_kept_as_a_chunk():
    chunks = _chunks("6. Mục sáu không có nội dung\n\n7. Mục bảy\n\nNội dung của mục bảy.")
    assert any("6. Mục sáu không có nội dung" in c.split("]\n\n", 1)[-1] for c in chunks)


# ---------------------------------------------------------------- document structure (H9) and Excel upload
def _docx(build) -> bytes:
    import docx

    d = docx.Document()
    build(d)
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


def test_sub_documents_with_repeated_article_numbers_keep_distinct_breadcrumbs():
    from solutions.rag.infrastructure.parsers.docx_parser import DocxDocumentParser

    def build(d):
        for doc_title in ("QUY CHẾ\nvề đánh giá", "QUY ĐỊNH\nvề tiêu chí"):
            d.add_heading(doc_title, level=1)
            d.add_heading("Chương I\nQUY ĐỊNH CHUNG", level=2)  # chapter typed on two lines
            d.add_heading("Điều 7. Nội dung", level=3)
            d.add_paragraph("2. Trình tự thực hiện")  # a numbered clause that looks like a heading
            d.add_paragraph(f"Nội dung điều 7 của {doc_title.split()[1]} " * 5)

    parsed = DocxDocumentParser().parse(_docx(build), "x.docx")
    chunks = DocumentChunker(hierarchical=True).chunk_document(parsed, "d", title="x")
    crumbs = {c.metadata["heading_path"] for c in chunks if "Nội dung điều 7" in c.text}
    assert any(p.startswith("QUY CHẾ") and "Điều 7" in p for p in crumbs)
    assert any(p.startswith("QUY ĐỊNH – về tiêu chí") and "Điều 7" in p for p in crumbs)
    assert not any(p.startswith(("QUY ĐỊNH CHUNG", "2. Trình tự")) for p in crumbs)


def test_xlsx_upload_is_accepted():
    from solutions.rag.application.use_cases.knowledge_use_case import ALLOWED_EXTENSIONS

    assert ".xlsx" in ALLOWED_EXTENSIONS


def test_search_text_leads_with_the_document_title():
    """Documents of one template: their chunks differ only by the document they belong to."""
    from solutions.rag.application.use_cases.ingestion_use_case import chunk_search_text

    text = "| Nhóm | Tên năng lực | Cấp độ |\n| --- | --- | --- |\n| Quản lý | Tư duy chiến lược | 3 |"
    a, b = chunk_search_text(text, {}, "Giảng viên chính"), chunk_search_text(text, {}, "Giảng viên")
    assert a.startswith("[Tài liệu: Giảng viên chính]") and a != b
    assert chunk_search_text("GIẢNG VIÊN CHÍNH – mục tiêu", {}, "Giảng viên chính").startswith("GIẢNG")  # already named


def _scan_pdf(pages: int) -> bytes:
    import pymupdf

    doc = pymupdf.open()
    for _ in range(pages):
        page = doc.new_page()
        pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 400, 500), 0)
        pix.set_rect(pix.irect, (255, 255, 255))
        page.insert_image(page.rect, pixmap=pix)
    return doc.tobytes()


def test_ocr_stops_at_the_per_document_page_budget(monkeypatch):
    from solutions.rag.config import rag_settings
    from solutions.rag.infrastructure.parsers.pdf_parser import PdfDocumentParser

    calls = []
    monkeypatch.setattr(PdfDocumentParser, "_try_ocr_fallback", lambda self, page: calls.append(1) or "Trang văn bản " * 5)
    monkeypatch.setattr(rag_settings, "ocr_max_pages", 2)
    parsed = PdfDocumentParser().parse(_scan_pdf(3), "scan.pdf")
    assert len(calls) == 2 and parsed.metadata["ocr_skipped_pages"] == [3]


def test_timed_out_ocr_page_is_skipped_without_the_unbounded_fallback(monkeypatch):
    import sys
    import types

    import pymupdf

    from solutions.rag.infrastructure.parsers.pdf_parser import PdfDocumentParser

    def timed_out(*_args, **_kwargs):
        raise RuntimeError("Tesseract process timeout")

    monkeypatch.setitem(sys.modules, "pytesseract", types.SimpleNamespace(image_to_string=timed_out))
    fallback = []
    monkeypatch.setattr(pymupdf.Page, "get_textpage_ocr", lambda *a, **k: fallback.append(1), raising=False)
    page = pymupdf.open(stream=_scan_pdf(1), filetype="pdf")[0]
    assert PdfDocumentParser()._try_ocr_fallback(page) is None and not fallback
