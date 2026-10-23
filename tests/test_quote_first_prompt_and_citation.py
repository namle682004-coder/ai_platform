"""
Unit & Integration Tests for FR-GEN-01, FR-GEN-03, GEN-RAG-01, GEN-RAG-03:
Quote-First Grounded Prompting, Citation Auditing, and Ghost-Citation Elimination.
"""


from solutions.rag.application.components.prompt_builder import (
    FEW_SHOT_CITATION_EXAMPLE,
    REFUSAL_MESSAGE,
    prompt_builder,
)
from solutions.rag.application.use_cases.chat_use_case import (
    _deduplicate_citations,
    _filter_attributed_citations,
)


class DummyChunk:
    def __init__(self, doc_id: str, title: str, text: str, score: float, page_number: int = 1):
        self.doc_id = doc_id
        self.title = title
        self.text = text
        self.score = score
        self.page_number = page_number
        self.metadata = {}


def test_quote_first_system_prompt_structure():
    """
    GEN-RAG-01 DoD:
    Prompt must enforce Quote-First discipline, exact refusal template, and few-shot citation format.
    """
    c1 = DummyChunk("doc_law_01", "Quy chế doanh nghiệp", "Điều 5: Nhân viên được nghỉ phép 12 ngày/năm.", 0.95)
    citations, system_prompt = prompt_builder.build_context_and_citations([c1])

    # 1. Quote-First rule
    assert "Kỷ luật Quote-First" in system_prompt
    assert "trích dẫn bằng chứng cụ thể" in system_prompt

    # 2. Citation markers [1], [2]
    assert "[1]" in system_prompt

    # 3. Standard refusal text
    assert REFUSAL_MESSAGE in system_prompt

    # 4. Few-shot example embedded
    assert FEW_SHOT_CITATION_EXAMPLE in system_prompt


def test_ghost_citation_elimination():
    """
    GEN-RAG-03 DoD (Zero Ghost Citations):
    If LLM output only cites [1], chunk [2] and hallucinated [99] MUST be eliminated
    from the returned response citations.
    """
    raw_citations = [
        {"index": 1, "doc_id": "doc_a", "title": "Doc A", "page_number": 1, "score": 0.95, "excerpt": "Excerpt A"},
        {"index": 2, "doc_id": "doc_b", "title": "Doc B", "page_number": 2, "score": 0.88, "excerpt": "Excerpt B"},
        {"index": 3, "doc_id": "doc_c", "title": "Doc C", "page_number": 3, "score": 0.82, "excerpt": "Excerpt C"},
    ]

    # LLM answer only mentions [1] and non-existent [99]
    answer = "Theo quy định mới, nhân viên được nghỉ phép 12 ngày có lương [1] và hưởng phụ cấp đặc biệt [99]."

    attributed = _filter_attributed_citations(raw_citations, answer, strategy="stuff")

    # Only chunk [1] is kept! Chunk [2] and [3] are pruned as ghost citations.
    assert len(attributed) == 1
    assert attributed[0]["index"] == 1
    assert attributed[0]["doc_id"] == "doc_a"


def test_multiple_citations_attributed_correctly():
    """
    When answer cites [1] and [3], both are retained in attributed citations.
    """
    raw_citations = [
        {"index": 1, "doc_id": "doc_a", "title": "Doc A", "page_number": 1, "score": 0.95, "excerpt": "Excerpt A"},
        {"index": 2, "doc_id": "doc_b", "title": "Doc B", "page_number": 2, "score": 0.88, "excerpt": "Excerpt B"},
        {"index": 3, "doc_id": "doc_c", "title": "Doc C", "page_number": 3, "score": 0.82, "excerpt": "Excerpt C"},
    ]

    answer = "Quy định phép năm là 12 ngày [1]. Ngoài ra phụ cấp thâm niên được cộng thêm [3]."

    attributed = _filter_attributed_citations(raw_citations, answer, strategy="stuff")

    assert len(attributed) == 2
    indices = [c["index"] for c in attributed]
    assert indices == [1, 3]


def test_deduplicate_citations_by_doc_and_excerpt():
    """
    Ensures citations from the same document and excerpt are deduplicated.
    """
    raw_citations = [
        {"index": 1, "doc_id": "doc_a", "title": "Doc A", "page_number": 1, "score": 0.95, "excerpt": "Quy chế A"},
        {"index": 2, "doc_id": "doc_a", "title": "Doc A", "page_number": 1, "score": 0.94, "excerpt": "Quy chế A"},
        {"index": 3, "doc_id": "doc_b", "title": "Doc B", "page_number": 2, "score": 0.85, "excerpt": "Quy chế B"},
    ]

    deduped = _deduplicate_citations(raw_citations)
    assert len(deduped) == 2
    doc_ids = [c["doc_id"] for c in deduped]
    assert doc_ids == ["doc_a", "doc_b"]
