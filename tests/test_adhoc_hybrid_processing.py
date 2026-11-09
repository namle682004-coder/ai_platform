"""
Unit tests verifying Hybrid Intelligence Ad-Hoc Document Processing (Session-level).
Tests:
1. Document classification in ad-hoc parse (direct_llm, structured_table, large_document).
2. Intelligent context extraction for large ad-hoc documents exceeding context limits.
3. System prompt specialization for tabular vs direct vs large ad-hoc QA.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock
from fastapi import UploadFile

from solutions.rag.application.dtos import RagChatRequestDTO
from solutions.rag.application.use_cases.chat_use_case import RagChatUseCase
from solutions.rag.interfaces.api.chat_router import parse_adhoc_document


def test_adhoc_direct_llm_classification():
    file_bytes = b"Day la noi dung tai lieu ngan gon de thu nghiem direct LLM.\nKhong co bang bieu."
    mock_file = MagicMock(spec=UploadFile)
    mock_file.filename = "tailieu_ngan.txt"
    mock_file.read = AsyncMock(return_value=file_bytes)

    res = asyncio.run(parse_adhoc_document(mock_file))
    assert res["filename"] == "tailieu_ngan.txt"
    assert res["strategy"] == "direct_llm"
    assert "Direct LLM" in res["summary"]


def test_adhoc_structured_table_classification():
    file_bytes = b"STT,Ten,DoanhThu\n1,Chi nhanh A,500\n2,Chi nhanh B,800\n3,Chi nhanh C,1200\n"
    mock_file = MagicMock(spec=UploadFile)
    mock_file.filename = "baocao_doanhthu.csv"
    mock_file.read = AsyncMock(return_value=file_bytes)

    res = asyncio.run(parse_adhoc_document(mock_file))
    assert res["filename"] == "baocao_doanhthu.csv"
    assert res["strategy"] == "structured_table"
    assert "B\xe1ng d\u1eef li\u1ec7u" in res["summary"] or "Bảng dữ liệu" in res["summary"]


def test_adhoc_large_document_extraction():
    # Construct a large text with distinct sections
    section_security = "### Phần 1: Quy định bảo mật thông tin\nMọi nhân viên phải tuân thủ chính sách mật khẩu 12 ký tự và không chia sẻ token."
    filler = "\n\n### Phần khác\nNội dung thông thường không liên quan đến bảo mật.\n" * 800
    section_end = "\n\n### Phần cuối: Kết luận bảo mật\nKiểm toán an ninh mạng được thực hiện định kỳ 6 tháng một lần."
    large_text = section_security + filler + section_end

    assert len(large_text) > 40000

    extracted = RagChatUseCase._extract_relevant_adhoc_context(
        query="chính sách bảo mật mật khẩu và kiểm toán",
        text=large_text,
        max_chars=5000,
    )

    assert len(extracted) <= 6000
    assert "Quy định bảo mật thông tin" in extracted
    assert "mật khẩu 12 ký tự" in extracted


def test_adhoc_messages_prompt_specialization():
    # 1. Structured table
    req_table = RagChatRequestDTO(
        query="Tính tổng doanh thu các chi nhánh",
        adhoc_context="STT | Chi nhánh | Doanh thu\n1 | A | 100\n2 | B | 200",
        adhoc_filename="doanh_thu.xlsx",
        adhoc_strategy="structured_table",
    )
    msgs, citations = RagChatUseCase._adhoc_messages(req_table, [])
    assert len(msgs) == 2
    assert "Chuyên gia Phân tích Dữ liệu Bảng tính" in msgs[0]["content"]

    # 2. Direct LLM
    req_direct = RagChatRequestDTO(
        query="Tóm tắt tài liệu",
        adhoc_context="Nội dung chính sách nghỉ phép năm 2026.",
        adhoc_filename="chinh_sach.docx",
        adhoc_strategy="direct_llm",
    )
    msgs_direct, _ = RagChatUseCase._adhoc_messages(req_direct, [])
    assert "Trợ lý AI Chuyên nghiệp" in msgs_direct[0]["content"]
    assert "NỘI DUNG TÀI LIỆU ĐÍNH KÈM" in msgs_direct[0]["content"]
