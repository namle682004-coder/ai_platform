"""
Regression tests for figures in answers (neutral sample data):
- numeric table questions are computed in code (min / max / difference / totals, multi-chunk tables);
- figures and counting units are verified against the passages, with a corrective regeneration;
- earlier answers' figures never reach the answer model;
- layout line breaks, table-of-contents lines and calendar labels are repaired before chunking.
"""

import asyncio
import json
from typing import Any, Dict, List, Tuple

from solutions.rag.application.components.answer_verifier import build_grounding
from solutions.rag.application.components.chunker import DocumentChunker
from solutions.rag.application.components.numeric_tables import (
    PLANNER_MARKER as NUMERIC_MARKER,
)
from solutions.rag.application.components.numeric_tables import (
    NumericPlan,
    compute_answer,
    parse_number,
    parse_numeric_tables,
)
from solutions.rag.application.components.query_analyzer import ANALYZER_MARKER
from solutions.rag.application.dtos import RagChatRequestDTO
from solutions.rag.application.use_cases.chat_use_case import RagChatUseCase
from solutions.rag.domain.entities import ParsedDocument, ParsedPage
from tests.test_rag_answer_pipeline import Embedder, Repo, ScoreReranker

TITLE = "Báo cáo bán hàng tuần"


def _chunk(idx: int, path: str, text: str) -> Dict[str, Any]:
    return {
        "id": f"rep-{idx}",
        "score": 0.5,
        "payload": {
            "doc_id": "doc_rep", "title": TITLE, "chunk_index": idx, "page_number": 1,
            "heading": path.split(">")[-1].strip(), "heading_path": path,
            "text": f"[Ngữ cảnh: {path}]\n\n{text}",
        },
    }


HEADER = "| Kênh | Ngày | Lượt xem | Bình luận |\n| --- | --- | --- | --- |\n"
CORPUS = [
    _chunk(0, "TỔNG QUAN", "Tuần này ghi nhận 7 đơn hàng mới, tương ứng với 4 khách hàng. Tổng cộng có 20 khách hàng."),
    _chunk(1, "NHÓM A > Sự kiện ra mắt", HEADER + "| Kênh Một | 02/11 | 45 | 3 |\n| Kênh Hai | 02/11 | 52 | 2 |\n| Kênh Ba | 02/11 | 3,2k | 180 |"),
    _chunk(2, "NHÓM A > Hội thảo", HEADER + "| Kênh Một | 03/11 | 12 | 1 |"),
    _chunk(3, "NHÓM B > Khuyến mãi", HEADER + "| Kênh Hai | 03/11 | 900 | 40 |"),
    _chunk(4, "THỐNG KÊ", "| STT | Kênh | Số bài | Loại |  |\n| --- | --- | --- | --- | --- |\n"
                          "| STT | Kênh | Số bài | Tốt | Xấu |\n|  | Kênh Một | 2 | 1 |  |\n|  | Kênh Một | 2 |  | 1 |"),
    _chunk(5, "THỐNG KÊ", "| STT | Kênh | Số bài | Loại |  |\n| --- | --- | --- | --- | --- |\n"
                          "|  | Kênh Hai | 1 | 1 |  |\n| Tổng |  | 3 | 2 | 1 |"),
]


# ---------------------------------------------------------------- numeric tables
def test_parse_number_reads_vietnamese_formats():
    assert parse_number("3,2k") == 3200
    assert parse_number("1.234") == 1234
    assert parse_number("12%") == 12
    assert parse_number("0") == 0
    assert parse_number("02/11") is None and parse_number("Kênh Một") is None


def test_tables_are_parsed_merged_and_totals_detected():
    tables = parse_numeric_tables(CORPUS)
    by_path = {t.path: t for t in tables}
    launch = by_path["NHÓM A > Sự kiện ra mắt"]
    assert [launch.columns[i] for i in launch.numeric_columns] == ["Lượt xem", "Bình luận"]
    assert [r.label for r in launch.rows] == ["Kênh Một", "Kênh Hai", "Kênh Ba"]
    stats = by_path["THỐNG KÊ"]  # two chunks, two-level header on the first only
    assert [stats.columns[i] for i in stats.numeric_columns] == ["Số bài", "Tốt", "Xấu"]
    assert [r.is_total for r in stats.rows] == [False, False, False, True]


def test_min_max_difference_are_computed_from_cells():
    launch = [t for t in parse_numeric_tables(CORPUS) if t.title == "Sự kiện ra mắt"]
    low, _ = compute_answer(NumericPlan(launch, "Bình luận", "min", "row", "sum", []))
    assert "**Kênh Hai**" in low and "**2**" in low
    diff, _ = compute_answer(NumericPlan(launch, "Bình luận", "diff", "row", "sum", []))
    assert "chênh lệch **178**" in diff
    group_a = [t for t in parse_numeric_tables(CORPUS) if t.path.startswith("NHÓM A")]
    best, sources = compute_answer(NumericPlan(group_a, "Lượt xem", "max", "table", "max", []))
    assert "**Sự kiện ra mắt**" in best and "**3,2k**" in best and len(sources) == 2
    least, _ = compute_answer(NumericPlan(group_a, "Lượt xem", "min", "table", "sum", []))
    assert "**Hội thảo**" in least


# ---------------------------------------------------------------- figure & unit grounding
def _grounding(question: str = ""):
    return build_grounding(CORPUS, CORPUS, allow_examples=False, language_guard=True, question=question)


def test_wrong_counting_unit_is_rejected_with_a_corrective_hint():
    g = _grounding()
    problem = g.sentence_problem("Tuần này có 7 khách hàng mới [1].")
    assert problem and problem.startswith("unit:")
    hint = g.hint(problem)
    assert "7 khách hàng" in hint and "4" in hint and "20" in hint
    assert g.sentence_problem("Có 4 khách hàng mới, tương ứng 7 đơn hàng [1].") is None


def test_invented_figures_and_dates_are_rejected():
    g = _grounding()
    assert g.sentence_problem("Kênh Ba có 1,5k lượt xem và 50 bình luận [1].").startswith("number:")
    assert g.sentence_problem("Kênh Ba có 3,2k lượt xem và 180 bình luận [1].") is None
    assert g.sentence_problem("Sự kiện diễn ra ngày 09/11 [1].").startswith("number:")
    assert g.sentence_problem("Sự kiện diễn ra ngày 02/11 [1].") is None
    # Figures the user wrote may be repeated (e.g. to correct a false premise).
    assert _grounding("Năm 2024 có bao nhiêu khách?").sentence_problem("Tài liệu không nói về năm 2024.") is None


# ---------------------------------------------------------------- chunker repair
def test_layout_breaks_toc_lines_and_calendar_labels_are_repaired():
    text = (
        "THỨ BA\n\nMỤC LỤC\n\nPHẦN A: TỔNG QUAN\t2\n\nPHẦN A: TỔNG QUAN\n\n"
        "Tuần này ghi nhận 7 đơn hàng mới, tương ứng với\n\n4 khách hàng, chiếm 20%. Doanh thu tăng."
    )
    doc = ParsedDocument(filename="r.docx", file_type="docx", pages=[ParsedPage(page_number=1, text=text)])
    chunks = DocumentChunker().chunk_document(doc, "d", title=TITLE)
    joined = "\n".join(c.text for c in chunks)
    assert "tương ứng với 4 khách hàng" in joined
    assert "\t2" not in joined
    assert all("THỨ BA" not in str((c.metadata or {}).get("heading", "")) for c in chunks)


# ---------------------------------------------------------------- use case
class FiguresLLM:
    """Analyzer / planner JSON by marker; scripted answers for generation calls (in order)."""

    def __init__(self, analysis: Dict[str, Any], answers: List[str], plan: Dict[str, Any] = None):
        self.analysis, self.answers, self.plan = analysis, list(answers), plan or {"applicable": False}
        self.generation_calls: List[List[Dict[str, str]]] = []

    async def generate(self, messages, model, temperature=0.2, max_tokens=1024, authorization=None) -> Tuple[str, int, int]:
        system = messages[0]["content"]
        if ANALYZER_MARKER in system:
            return json.dumps(self.analysis, ensure_ascii=False), 5, 5
        if NUMERIC_MARKER in system:
            return json.dumps(self.plan, ensure_ascii=False), 5, 5
        if "[TABLE_PLANNER]" in system:
            return '{"applicable": false}', 5, 5
        self.generation_calls.append(messages)
        return (self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]), 5, 5

    async def stream_generate(self, messages, model, temperature=0.2, max_tokens=1024, authorization=None):
        text, _, _ = await self.generate(messages, model, temperature, max_tokens, authorization)
        for i in range(0, len(text), 4):
            yield text[i:i + 4]


class Store:
    async def search(self, **kwargs):
        return [dict(c) for c in CORPUS]

    async def fetch_document_chunks(self, doc_id, tenant_id, user_role="user", limit=300):
        return [dict(c) for c in CORPUS]


def _use_case(llm):
    return RagChatUseCase(Store(), Embedder(), llm, Repo(), reranker_service=ScoreReranker())


def test_lowest_question_is_computed_not_generated():
    launch_id = next(t.id for t in parse_numeric_tables(CORPUS) if t.title == "Sự kiện ra mắt")
    llm = FiguresLLM(
        {"intent": "document_question", "standalone_query": "Kênh nào có ít bình luận nhất ở sự kiện ra mắt?",
         "aggregate": "min", "focus": ["bình luận"]},
        ["Kênh Ba có 1,5k lượt xem, 50 bình luận [1]."],
        {"applicable": True, "tables": [launch_id], "column": "Bình luận", "operation": "min", "unit": "row"},
    )
    resp = asyncio.run(_use_case(llm).execute(RagChatRequestDTO(query="Thế ít nhất thì sao?", similarity_threshold=0.0)))
    assert resp.intent == "QA_NUMERIC"
    assert "**Kênh Hai**" in resp.answer and "**2**" in resp.answer and "1,5k" not in resp.answer
    assert llm.generation_calls == [] and resp.citations


def test_wrong_unit_answer_is_corrected_by_regeneration():
    llm = FiguresLLM(
        {"intent": "document_question", "standalone_query": "Có bao nhiêu khách hàng mới?", "focus": ["khách hàng mới"]},
        ["Tuần này có 7 khách hàng mới [1].", "Tuần này có 4 khách hàng mới, tương ứng với 7 đơn hàng [1]."],
    )
    resp = asyncio.run(_use_case(llm).execute(RagChatRequestDTO(query="Có bao nhiêu khách hàng mới?", similarity_threshold=0.0)))
    assert "4 khách hàng" in resp.answer and "7 khách hàng" not in resp.answer
    correction = llm.generation_calls[-1][-1]["content"]
    assert "KIỂM TRA LẠI" in correction and "7 khách hàng" in correction


def test_streamed_wrong_unit_answer_is_corrected():
    llm = FiguresLLM(
        {"intent": "document_question", "standalone_query": "Có bao nhiêu khách hàng mới?", "focus": ["khách hàng mới"]},
        ["Tuần này có 7 khách hàng mới [1].", "Tuần này có 4 khách hàng mới [1]."],
    )

    async def run():
        out = []
        async for ev in _use_case(llm).stream_execute(RagChatRequestDTO(query="Có bao nhiêu khách hàng mới?", similarity_threshold=0.0)):
            if ev.startswith("data: "):
                out.append(json.loads(ev[6:]))
        return out

    events = asyncio.run(run())
    text = "".join(e.get("token", "") for e in events)
    assert "4 khách hàng" in text and "7 khách hàng" not in text


def test_previous_answer_figures_do_not_reach_the_answer_model():
    llm = FiguresLLM(
        {"intent": "document_question", "standalone_query": "Hội thảo có bao nhiêu lượt xem?", "focus": ["hội thảo"]},
        ["Hội thảo có 12 lượt xem [1]."],
    )
    history = [
        {"role": "user", "content": "Sự kiện ra mắt có bao nhiêu lượt xem?"},
        {"role": "assistant", "content": "Kênh Ba có 3,2k lượt xem [1]."},
    ]
    asyncio.run(_use_case(llm).execute(RagChatRequestDTO(query="Còn hội thảo?", history=history, similarity_threshold=0.0)))
    sent = json.dumps(llm.generation_calls[-1], ensure_ascii=False)
    history_part = sent.split("TÀI LIỆU")[0] + json.dumps(llm.generation_calls[-1][1:-1], ensure_ascii=False)
    assert "3,2k lượt xem [1]" not in history_part
    assert "Sự kiện ra mắt có bao nhiêu lượt xem?" in sent
