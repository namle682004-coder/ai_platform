"""
Unit tests for bulk Excel import of Q&A pairs (Requirement #19).
"""

import asyncio
import io
from unittest.mock import AsyncMock

import openpyxl
import pytest

from solutions.rag.application.dtos import QACreateResponseDTO
from solutions.rag.application.use_cases.knowledge_use_case import KnowledgeManagementUseCase, qa_sheet_columns


def _xlsx(rows):
    wb = openpyxl.Workbook()
    for r in rows:
        wb.active.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _importer(existing=()):
    uc = KnowledgeManagementUseCase.__new__(KnowledgeManagementUseCase)
    uc.list_qa = AsyncMock(return_value=[{"question": q} for q in existing])
    uc.ingest_qa = AsyncMock(side_effect=lambda **kw: QACreateResponseDTO(
        status="created", qa_id=f"qa_{kw['question'][:5]}", indexing_latency_ms=1.0, qdrant_point_id="p"))
    return uc


def test_columns_are_found_by_whole_words_whatever_their_order():
    # "Danh mục" / "Category" contain the letter "a": they are not the answer column.
    assert qa_sheet_columns(["Danh mục", "Câu hỏi", "Câu trả lời"]) == (1, 2, 0, None)
    assert qa_sheet_columns(["Category", "Question", "Answer", "Variants"]) == (1, 2, 0, 3)
    # "Câu hỏi tương tự" is the variations column, not a second question column.
    assert qa_sheet_columns(["Câu hỏi tương tự", "Câu hỏi", "Đáp án"]) == (1, 2, None, 0)
    assert qa_sheet_columns(["Q", "A"]) == (0, 1, None, None)
    assert qa_sheet_columns(["STT", "Ghi chú"])[:2] == (None, None)


def test_a_sheet_without_question_and_answer_columns_is_refused_with_a_reason():
    with pytest.raises(ValueError, match="Câu hỏi"):
        asyncio.run(_importer().import_qa_from_excel(_xlsx([["STT", "Ghi chú"], [1, "x"]]), "x.xlsx", tenant_id="t"))


def test_reimporting_a_file_does_not_duplicate_pairs():
    rows = [["Danh mục", "Câu hỏi", "Câu trả lời"], ["Kỹ thuật", "Cài plugin ký số?", "Tải và cài đặt."],
            ["Hóa đơn", "Tra cứu hóa đơn?", "Vào mục tra cứu."]]
    uc = _importer(existing=["cài plugin KÝ SỐ?"])  # same question, other case / punctuation
    res = asyncio.run(uc.import_qa_from_excel(_xlsx(rows), "qa.xlsx", tenant_id="t"))
    assert res["imported"] == 1 and res["skipped_existing"] == 1
    call = uc.ingest_qa.call_args_list[0].kwargs
    assert call["question"] == "Tra cứu hóa đơn?" and call["answer"] == "Vào mục tra cứu." and call["category"] == "Hóa đơn"


def test_bulk_import_qa_from_excel():
    async def _test():
        # 1. Create in-memory Excel workbook with 3 questions
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["Câu hỏi", "Câu trả lời", "Danh mục", "Biến thể"])
        ws.append(["Cài đặt plugin ký số như thế nào?", "Vào menu Cài đặt > Tải plugin > Cài đặt.", "Kỹ thuật", "cách cài plugin | lỗi plugin"])
        ws.append(["Cách tra cứu hóa đơn?", "Vào tra cứu hóa đơn điện tử.", "Hóa đơn", "tra cuu hoa don"])
        ws.append(["Hotline hỗ trợ?", "Hotline 1900 xxxx", "CSKH", ""])

        buf = io.BytesIO()
        wb.save(buf)
        excel_bytes = buf.getvalue()

        uc = KnowledgeManagementUseCase.__new__(KnowledgeManagementUseCase)
        uc.list_qa = AsyncMock(return_value=[])
        uc.ingest_qa = AsyncMock(side_effect=[
            QACreateResponseDTO(status="created", qa_id="qa_1", indexing_latency_ms=10.0, qdrant_point_id="pt_1"),
            QACreateResponseDTO(status="created", qa_id="qa_2", indexing_latency_ms=10.0, qdrant_point_id="pt_2"),
            QACreateResponseDTO(status="created", qa_id="qa_3", indexing_latency_ms=10.0, qdrant_point_id="pt_3"),
        ])

        res = await uc.import_qa_from_excel(excel_bytes, "qa.xlsx", tenant_id="tenant_dvkh")

        assert res["total_rows"] == 3
        assert res["imported"] == 3
        assert res["failed"] == 0
        assert len(res["items"]) == 3
        assert uc.ingest_qa.call_count == 3

        # Verify call arguments of first row
        first_call = uc.ingest_qa.call_args_list[0].kwargs
        assert first_call["question"] == "Cài đặt plugin ký số như thế nào?"
        assert first_call["answer"] == "Vào menu Cài đặt > Tải plugin > Cài đặt."
        assert first_call["category"] == "Kỹ thuật"
        assert first_call["question_variations"] == ["cách cài plugin", "lỗi plugin"]
        assert first_call["tenant_id"] == "tenant_dvkh"

    asyncio.run(_test())
