"""
Unit & Integration Test Suite for Enterprise Acronym & Glossary Harvester.
Verifies production readiness of multi-stage harvesting, derivation, enrichment,
and query expansion across Vietnamese enterprise documents.
"""

from solutions.rag.application.components.acronym_harvester import (
    AcronymHarvester,
    detect_candidates,
    enrich_chunk_for_embedding,
    expand_query,
    glossary_for_prompt,
    harvest_explicit,
    harvest_glossary,
)


def test_stage_0_detect_candidates():
    """Verify candidate detection, Roman numeral and document code handling, heading exclusion."""
    text = """
    CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM
    Độc lập - Tự do - Hạnh phúc

    QUY CHẾ TỔ CHỨC VÀ HOẠT ĐỘNG
    Số: 123/QĐ-BQLDA ngày 15/01/2026

    Điều I. Phạm vi áp dụng
    BQLDA phối hợp cùng TP.HCM và các đơn vị TTr để triển khai PCCC.
    Mã quy trình: QT-NS-05 phiên bản v2.0.
    Các khoản chi tính bằng VND hoặc USD.
    """
    cands = detect_candidates(text)
    abbr_keys = set(cands.keys())

    # Acronym candidates detected
    assert "BQLDA" in abbr_keys
    assert "TP.HCM" in abbr_keys or "TPHCM" in abbr_keys
    assert "TTr" in abbr_keys
    assert "PCCC" in abbr_keys

    # Excluded noise
    assert "VND" not in abbr_keys
    assert "USD" not in abbr_keys
    assert "I" not in abbr_keys  # Roman numeral
    assert "VIỆT" not in abbr_keys  # Heading word

    # Code classification
    assert cands["123/QĐ-BQLDA"].is_code is True
    assert cands["QT-NS-05"].is_code is True
    assert cands["BQLDA"].is_code is False


def test_stage_1_explicit_section_and_table_harvesting():
    """Verify harvesting from 'Điều 2. Giải thích từ ngữ' and markdown table formats."""
    text = """
    Điều 2. Giải thích từ ngữ
    Trong văn bản này, các từ ngữ dưới đây được hiểu như sau:
    1. BQL: Ban Quản lý Tòa nhà
    2. BBBG - Biên bản bàn giao tài sản
    3. HĐTV là Hội đồng thành viên công ty;
    | KHLCNT | Kế hoạch lựa chọn nhà thầu |
    | HSMT | Hồ sơ mời thầu xây lắp |

    Điều 3. Trách nhiệm của các bên
    BQL có trách nhiệm lập BBBG theo KHLCNT đã phê duyệt.
    """
    glossary, sources = harvest_explicit(text)

    assert glossary["BQL"] == "Ban Quản lý Tòa nhà"
    assert sources["BQL"] == "section"
    assert glossary["BBBG"] == "Biên bản bàn giao tài sản"
    assert glossary["HĐTV"] == "Hội đồng thành viên công ty"
    assert glossary["KHLCNT"] == "Kế hoạch lựa chọn nhà thầu"
    assert glossary["HSMT"] == "Hồ sơ mời thầu xây lắp"


def test_stage_1_explicit_inline_harvesting():
    """Verify inline parenthetical patterns: Full (ABBR), ABBR (Full), and 'sau đây gọi tắt là'."""
    text = """
    Tổng công ty Điện lực miền Bắc (sau đây gọi tắt là EVNNPC) thông báo tới các đối tác.
    Đại diện Ban Chỉ đạo Phòng chống Dịch bệnh (BCĐPCD) đã ký biên bản.
    Theo báo cáo của P.KHĐT (Phòng Kế hoạch Đầu tư), dự án đã hoàn thành nghiệm thu.
    """
    glossary, sources = harvest_explicit(text)

    assert glossary["EVNNPC"] == "Tổng công ty Điện lực miền Bắc"
    assert sources["EVNNPC"] == "inline"
    assert "BCĐPCD" in glossary
    assert "Ban Chỉ đạo Phòng chống Dịch bệnh" in glossary["BCĐPCD"]
    assert glossary["P.KHĐT"] == "Phòng Kế hoạch Đầu tư"


def test_stage_2_derive_from_text_with_digraphs_and_connectors():
    """Verify deriving acronym definitions from text windows without parentheses."""
    text = """
    Để bảo đảm an toàn, Ban An toàn Lao động cần kiểm tra định kỳ nhà xưởng.
    Hôm qua, BATLĐ đã phát hiện 3 điểm cần khắc phục tại phân xưởng 1.
    Bộ phận phụ trách cũng đã gửi một Tờ trình lên Ban Giám đốc.
    TTr đề xuất duyệt kinh phí trang bị bảo hộ mới.
    """
    cands = detect_candidates(text)
    # BATLĐ and TTr should be detected
    assert "BATLĐ" in cands
    assert "TTr" in cands

    harvester = AcronymHarvester()
    res = harvester.harvest(text, use_global_dict=False)

    # BATLĐ derived from "Ban An toàn Lao động"
    assert "BATLĐ" in res.glossary
    assert "Ban An toàn Lao động" in res.glossary["BATLĐ"]
    assert res.entries["BATLĐ"].source == "derived"
    assert res.entries["BATLĐ"].confidence >= 0.7

    # TTr derived from "Tờ trình" using Vietnamese digraph 'Tr'
    assert "TTr" in res.glossary
    assert "Tờ trình" in res.glossary["TTr"]
    assert res.entries["TTr"].source == "derived"


def test_stage_3_global_and_tenant_dictionary_fallback():
    """Verify integration with vietnamese_resources global dictionary and tenant overrides."""
    text = """
    Nhân viên cần nộp hồ sơ hưởng BHXH và BHYT tại cơ quan quản lý.
    Căn cứ theo quyết định của HĐQT về việc điều chỉnh kế hoạch năm 2026.
    Phòng ban ký kết HĐTV theo mẫu nội bộ.
    """
    harvester = AcronymHarvester()
    # Provide a tenant override for ambiguous acronym HĐTV
    tenant_dict = {"HĐTV": "Hợp đồng thử việc nội bộ"}
    res = harvester.harvest(text, tenant_dict=tenant_dict, use_global_dict=True)

    # Global enterprise terms
    assert res.glossary.get("BHXH") == "Bảo hiểm xã hội"
    assert res.glossary.get("BHYT") == "Bảo hiểm y tế"
    assert res.glossary.get("HĐQT") == "Hội đồng quản trị"

    # Tenant override wins
    assert res.glossary.get("HĐTV") == "Hợp đồng thử việc nội bộ"


def test_stage_4_batched_llm_resolver_integration():
    """Verify batched 1-shot LLM fallback for unresolved acronyms."""
    text = """
    Tại khu công nghiệp Sài Đồng, đại diện CTYABC đã tham gia hội nghị logistics.
    Hội đồng thẩm định đánh giá cao đề án của CTYABC.
    """
    def mock_llm_resolver(prompt: str) -> str:
        assert "CTYABC" in prompt
        return '{"CTYABC": "Công ty Cổ phần Ánh Bình Chuẩn"}'

    harvester = AcronymHarvester()
    res = harvester.harvest(text, llm_resolver=mock_llm_resolver, use_global_dict=False)

    assert res.glossary.get("CTYABC") == "Công ty Cổ phần Ánh Bình Chuẩn"
    assert res.entries["CTYABC"].source == "llm"


def test_enrich_chunk_for_embedding_cross_chunk_disconnection():
    """Verify that enrich_chunk_for_embedding resolves Cross-Chunk Disconnection."""
    glossary = {
        "BQLDA": "Ban Quản lý Dự án",
        "HĐLĐ": "Hợp đồng lao động",
        "TNLĐ": "Tai nạn lao động",
    }
    chunk_text = "BQLDA có trách nhiệm bồi thường chi phí khi xảy ra sự cố TNLĐ trong ca trực."
    enriched = enrich_chunk_for_embedding(chunk_text, glossary)

    # Prefix contains definitions of present acronyms
    assert enriched.startswith("[")
    assert "BQLDA: Ban Quản lý Dự án" in enriched
    assert "TNLĐ: Tai nạn lao động" in enriched
    # HĐLĐ not in chunk -> not prefixed
    assert "HĐLĐ" not in enriched.split("\n")[0]
    # Original chunk text follows newline
    assert chunk_text in enriched


def test_expand_query_bidirectional():
    """Verify bi-directional query expansion (ABBR -> Full and Full -> ABBR)."""
    glossary = {
        "BBBG": "Biên bản bàn giao",
        "BQL": "Ban Quản lý",
        "MST": "Mã số thuế",
    }

    # Direction 1: ABBR -> Full
    q1 = "Thời hạn ký BBBG là bao lâu?"
    expanded_1 = expand_query(q1, glossary)
    assert "BBBG (Biên bản bàn giao)" in expanded_1

    # Direction 2: Full -> ABBR (helps BM25 match chunks containing only acronyms)
    q2 = "Thủ tục nộp hồ sơ lên Ban Quản lý để tra cứu Mã số thuế"
    expanded_2 = expand_query(q2, glossary)
    assert "Ban Quản lý (BQL)" in expanded_2
    assert "Mã số thuế (MST)" in expanded_2


def test_glossary_for_prompt_token_saving():
    """Verify that glossary_for_prompt only includes relevant definitions."""
    glossary = {
        "BBBG": "Biên bản bàn giao",
        "BQL": "Ban Quản lý",
        "BHXH": "Bảo hiểm xã hội",
        "PCCC": "Phòng cháy chữa cháy",
        "KPI": "Chỉ số hiệu quả",
    }
    query = "Quy định về thời hạn lập BBBG"
    chunks_text = "Đại diện BQL sẽ kiểm tra hiện trường trước khi ký nhận."

    prompt_glossary = glossary_for_prompt(glossary, query=query, chunks_text=chunks_text)

    # Only BBBG and BQL are referenced
    assert "BBBG = Biên bản bàn giao" in prompt_glossary
    assert "BQL = Ban Quản lý" in prompt_glossary
    # BHXH, PCCC, KPI should be pruned to save prompt tokens
    assert "BHXH" not in prompt_glossary
    assert "PCCC" not in prompt_glossary
    assert "KPI" not in prompt_glossary


def test_pipeline_coverage_report():
    """Verify coverage report metrics and calculations."""
    text = """
    Điều 2. Giải thích từ ngữ
    1. BQL: Ban Quản lý Tòa nhà
    2. BBBG: Biên bản bàn giao

    BQL và BBBG được sử dụng trong hợp đồng này.
    BQL chịu trách nhiệm lưu trữ BBBG.
    Đơn vị XYZABC chưa được định nghĩa.
    """
    res = harvest_glossary(text)
    report = res.report

    assert report.unique_total >= 3
    assert report.unique_resolved >= 2
    assert report.unique_coverage >= 0.60
    assert report.mention_total >= 5
    assert report.mention_resolved >= 4
    assert "section" in report.by_source
