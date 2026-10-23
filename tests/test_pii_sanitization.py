"""
Unit and integration test suite for ING-RAG-07:
Automated PII Masking & Sensitive Data Sanitization (PDPD / Decree 13/2023/NĐ-CP Compliance).

DoD Verification:
1. 0% PII leakage in chunks and Qdrant payloads (Email, Phone, CCCD, Secret Keys, Passwords).
   Standard tokens: [EMAIL_REDACTED], [PHONE_REDACTED], [ID_REDACTED], [SECRET_KEY_REDACTED].
2. Zero false positive redaction on legal document citations (123/2020/NĐ-CP, 45/2019/TT-BTC),
   article numbers (Điều 12, Khoản 3, Mục 2.1), and dates (2024-10-12, 15/04/2026).
"""

from common.chunking import PiiSanitizer
from solutions.rag.domain.entities import ParsedDocument, ParsedPage
from solutions.rag.application.components.chunker import DocumentChunker


def test_pii_sanitizer_all_entities():
    """Verify masking of all 4 sensitive entity types with standardized tokens."""
    sample_text = (
        "Thông tin nhân viên:\n"
        "- Email: nguyen.van.a@techbank.com.vn\n"
        "- Điện thoại cá nhân: 0912345678 hoặc +84987654321\n"
        "- Số CCCD: 001234567890\n"
        "- API Secret Key: sk-proj-1234567890abcdef1234567890\n"
        "- Mật khẩu hệ thống: password: SuperSecretAdminPass123\n"
        "- Token truy cập: aip_live_a1b2c3d4e5f6g7h8\n"
    )

    sanitized = PiiSanitizer.sanitize(sample_text)

    # 1. Email redacted
    assert "nguyen.van.a@techbank.com.vn" not in sanitized
    assert "[EMAIL_REDACTED]" in sanitized

    # 2. Phone redacted
    assert "0912345678" not in sanitized
    assert "+84987654321" not in sanitized
    assert "[PHONE_REDACTED]" in sanitized

    # 3. CCCD redacted
    assert "001234567890" not in sanitized
    assert "[ID_REDACTED]" in sanitized

    # 4. Secret keys & Passwords redacted
    assert "sk-proj-1234567890abcdef1234567890" not in sanitized
    assert "SuperSecretAdminPass123" not in sanitized
    assert "aip_live_a1b2c3d4e5f6g7h8" not in sanitized
    assert "[SECRET_KEY_REDACTED]" in sanitized


def test_pii_zero_false_positive_on_legal_citations_and_dates():
    """
    ING-RAG-07 DoD 2:
    Guarantees legal document numbers, article citations, and dates are NEVER redacted.
    """
    legal_text = (
        "Căn cứ Nghị định số 123/2020/NĐ-CP ngày 19/10/2020 của Chính phủ quy định về hóa đơn, chứng từ.\n"
        "Căn cứ Thông tư số 78/2021/TT-BTC hướng dẫn thực hiện một số điều của Luật Quản lý thuế.\n"
        "Quyết định số 145/QĐ-UBND ban hành ngày 2024-05-15.\n"
        "Theo quy định tại Điều 12, Khoản 3 và Mục 2.1 của Quy chế nội bộ."
    )

    sanitized = PiiSanitizer.sanitize(legal_text)

    # Legal doc numbers must remain 100% intact
    assert "123/2020/NĐ-CP" in sanitized
    assert "78/2021/TT-BTC" in sanitized
    assert "145/QĐ-UBND" in sanitized

    # Dates must remain intact
    assert "19/10/2020" in sanitized
    assert "2024-05-15" in sanitized

    # Article/Section references must remain intact
    assert "Điều 12" in sanitized
    assert "Khoản 3" in sanitized
    assert "Mục 2.1" in sanitized

    # No false redactions occurred
    assert "[ID_REDACTED]" not in sanitized
    assert "[PHONE_REDACTED]" not in sanitized
    assert "[EMAIL_REDACTED]" not in sanitized
    assert "[SECRET_KEY_REDACTED]" not in sanitized


def test_chunker_end_to_end_pii_masking():
    """Verify DocumentChunker sanitizes all chunks end-to-end."""
    doc_text = (
        "# BIÊN BẢN BÀN GIAO TÀI KHOẢN VÀ HỆ THỐNG\n\n"
        "Căn cứ hợp đồng số 88/2026/HĐ-CNTT ký ngày 01/01/2026.\n\n"
        "## 1. Thông Tin Bên Nhận\n\n"
        "Họ và tên: Trần Thị B\n"
        "Số định danh CCCD: 079123456789\n"
        "Email công vụ: tran.thi.b@doanhnghiep.vn\n"
        "Hotline liên hệ: 0909123456\n\n"
        "## 2. Thông Tin Khởi Tạo Dịch Vụ\n\n"
        "Mật khẩu ban đầu: mật khẩu: KhởiTạo@2026!\n"
        "Khóa bí mật kết nối cổng API: sk-11223344556677889900aabbcc\n"
    )
    doc = ParsedDocument(filename="handover_protocol.md", file_type="markdown", pages=[ParsedPage(page_number=1, text=doc_text)])

    chunker = DocumentChunker(child_chunk_size_chars=350, mask_pii=True)
    chunks = chunker.chunk_document(doc, doc_id="doc_handover_01")

    assert len(chunks) >= 2

    full_chunks_text = "\n".join(c.text for c in chunks)

    # 1. PII entities must be completely redacted
    assert "079123456789" not in full_chunks_text
    assert "tran.thi.b@doanhnghiep.vn" not in full_chunks_text
    assert "0909123456" not in full_chunks_text
    assert "KhởiTạo@2026!" not in full_chunks_text
    assert "sk-11223344556677889900aabbcc" not in full_chunks_text

    # Standard replacement tokens must be present
    assert "[ID_REDACTED]" in full_chunks_text
    assert "[EMAIL_REDACTED]" in full_chunks_text
    assert "[PHONE_REDACTED]" in full_chunks_text
    assert "[SECRET_KEY_REDACTED]" in full_chunks_text

    # 2. Legal contract number and dates must remain intact
    assert "88/2026/HĐ-CNTT" in full_chunks_text
    assert "01/01/2026" in full_chunks_text
