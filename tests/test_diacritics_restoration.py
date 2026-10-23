"""
Unit test suite for Audit Item 7: Vietnamese Diacritics Restoration, Acronyms & Model NLP Normalization.
Verifies:
1. Lexicons decoupled into vietnamese_resources.py.
2. Diacritic-tolerant phrase matching: partially accented queries (e.g. 'hướng dẫn lam hddt') are restored properly.
3. Expanded enterprise acronyms and casing normalization (e.g. 'hddt' -> 'HĐĐT', 'mst' -> 'MST', 'bhxh' -> 'BHXH').
4. Missing enterprise phrases (cong ty, to chuc, giao dich, thu tuc hanh chinh, co quan, tai lieu, etc.) are restored.
5. Ambiguous words (co, nam, tai, do) are not blindly corrupted in isolation.
6. Case preservation: preserves lower, title, and upper casing.
7. Latency SLA: execution finishes in < 0.5ms.
8. Tier 3 Model NLP Normalization hook.
"""

import time
import pytest
from solutions.rag.application.components.query_rewriter import RagQueryRewriter
from solutions.rag.application.components.vietnamese_resources import (
    ENTERPRISE_ACRONYMS,
    ACRONYM_CASING_MAP,
    DIACRITICS_PHRASE_MAP,
    DIACRITICS_WORD_MAP,
)


def test_lexicons_decoupled_and_populated():
    """Verify that lexicons are properly decoupled and contain extensive enterprise terminology."""
    assert len(ENTERPRISE_ACRONYMS) >= 40
    assert len(ACRONYM_CASING_MAP) >= 30
    assert len(DIACRITICS_PHRASE_MAP) >= 100
    assert "MST" in ENTERPRISE_ACRONYMS
    assert "HĐĐT" in ENTERPRISE_ACRONYMS
    assert "BHXH" in ENTERPRISE_ACRONYMS
    assert "cong ty" in DIACRITICS_PHRASE_MAP
    assert "to chuc" in DIACRITICS_PHRASE_MAP
    assert "giao dich" in DIACRITICS_PHRASE_MAP
    assert "thu tuc hanh chinh" in DIACRITICS_PHRASE_MAP


def test_mixed_partially_accented_restoration():
    """
    Audit Item 7 Bug Fix:
    Diacritic-tolerant regex matches partially accented queries like 'hướng dẫn lam hddt'
    restoring 'lam' -> 'làm' and 'hddt' -> 'HĐĐT'.
    """
    input_text = "hướng dẫn lam hddt"
    restored = RagQueryRewriter.restore_vietnamese_diacritics(input_text)
    assert restored == "hướng dẫn làm HĐĐT"

    input_text_2 = "quy định ve nghi phep nam"
    restored_2 = RagQueryRewriter.restore_vietnamese_diacritics(input_text_2)
    assert restored_2 == "quy định về nghỉ phép năm"


def test_enterprise_phrases_restoration():
    """
    Phrases that were previously missing from dictionary must be restored correctly.
    """
    queries = {
        "cong ty co phan": "công ty cổ phần",
        "to chuc giao dich tai chinh": "tổ chức giao dịch tài chính",
        "thu tuc hanh chinh tai co quan nha nuoc": "thủ tục hành chính tại cơ quan nhà nước",
        "kiem toan bao cao tai chinh": "kiểm toán báo cáo tài chính",
        "chuc nang va nhiem vu cua truong phong": "chức năng và nhiệm vụ của trưởng phòng",
        "che do nghi thai san va tien thuong tet": "chế độ nghỉ thai sản và tiền thưởng tết",
    }

    for raw, expected in queries.items():
        res = RagQueryRewriter.restore_vietnamese_diacritics(raw)
        assert res.lower() == expected.lower(), f"Failed for '{raw}': got '{res}', expected '{expected}'"


def test_ambiguous_words_not_corrupted_in_isolation():
    """
    Words like 'co', 'nam', 'tai', 'do' should NOT be in DIACRITICS_WORD_MAP
    to prevent false single-word mutations without context.
    """
    assert "co" not in DIACRITICS_WORD_MAP
    assert "nam" not in DIACRITICS_WORD_MAP
    assert "tai" not in DIACRITICS_WORD_MAP
    assert "do" not in DIACRITICS_WORD_MAP


def test_acronym_expansion_and_casing():
    """Verify acronym casing and expansion functions."""
    assert RagQueryRewriter.restore_vietnamese_diacritics("quy dinh bhxh va bhyt") == "quy định BHXH và BHYT"
    assert RagQueryRewriter.restore_vietnamese_diacritics("tra cuu mst va hddt") == "tra cứu MST và HĐĐT"
    assert RagQueryRewriter.restore_vietnamese_diacritics("ho so dkkd va cccd") == "hồ sơ ĐKKD và CCCD"

    expanded = RagQueryRewriter.expand_acronyms("Tra cứu MST và HĐĐT")
    assert "Mã số thuế" in expanded
    assert "Hóa đơn điện tử" in expanded


def test_case_preservation():
    """Verify that uppercase and titlecase are preserved during restoration."""
    res_title = RagQueryRewriter.restore_vietnamese_diacritics("Cong Ty Co Phan")
    assert res_title == "Công Ty Cổ Phần"

    res_upper = RagQueryRewriter.restore_vietnamese_diacritics("CONG TY")
    assert res_upper == "CÔNG TY"


def test_has_unaccented_words_detector():
    """Verify heuristic detection of unaccented words for Tier 3 model trigger."""
    assert RagQueryRewriter.has_unaccented_words("hướng dẫn làm HĐĐT") is False
    assert RagQueryRewriter.has_unaccented_words("huong dan lam") is True
    # English/tech terms should not trigger
    assert RagQueryRewriter.has_unaccented_words("tra cứu API Qdrant") is False


@pytest.mark.anyio
async def test_model_normalization_tier_3_integration():
    """Verify Tier 3 model normalization hook when llm_port is available."""
    class MockLlmPort:
        async def generate(self, messages, model, temperature=0.0, max_tokens=64):
            return "hướng dẫn cài đặt phần mềm kế toán", 10, 10

    mock_llm = MockLlmPort()
    res = await RagQueryRewriter.normalize_diacritics_with_model(
        "huong dan cai dat phan mem ke toan",
        llm_port=mock_llm,
    )
    assert res == "hướng dẫn cài đặt phần mềm kế toán"


def test_diacritics_restoration_latency():
    """Verify that diacritics restoration completes in sub-millisecond time (< 0.5ms)."""
    text = "huong dan lam thu tuc hanh chinh tai co quan nha nuoc va nop thue thu nhap ca nhan"

    # Warmup
    RagQueryRewriter.restore_vietnamese_diacritics(text)

    # Best of 5 runs to eliminate CPU scheduling spikes in WSL
    times = []
    for _ in range(5):
        t0 = time.perf_counter()
        res = RagQueryRewriter.restore_vietnamese_diacritics(text)
        t1 = time.perf_counter()
        times.append((t1 - t0) * 1000)

    elapsed_ms = min(times)
    assert elapsed_ms < 0.5, f"Restoration took {elapsed_ms:.3f}ms, expected < 0.5ms"
    assert "hướng dẫn làm" in res
    assert "thủ tục hành chính" in res
    assert "cơ quan nhà nước" in res
    assert "thuế thu nhập cá nhân" in res
