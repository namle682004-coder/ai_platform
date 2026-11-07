"""
Questions over tables answered in code from the stored tables (synthetic fixtures of the failure classes):
listing every row marked in one column of a two-level header (posts by sentiment), counting them, summing a
column of merged cells without double counting, reading the same table in every document of a template, and
never taking a data row for a totals row.
"""

from solutions.rag.application.components.table_query import (
    Condition as C,
    TableQuery as Q,
    parse_plan,
    planner_messages,
    render_result,
    run_query,
)
from solutions.rag.application.components.table_store import extract_tables, total_rows
from solutions.rag.domain.entities import ParsedPage
from solutions.rag.infrastructure.parsers.table_grid import GridCell as G
from solutions.rag.infrastructure.parsers.table_grid import render_table


def _bulletin_page():
    """Posts table: source merged over its posts, 'Group' header over three marker columns, totals row."""
    header = [G("STT", 1), G("Nguồn", 2), G("Số bài", 3), G("Tiêu đề", 4), G("Nhóm", 5), G("Nhóm", 5), G("Nhóm", 5)]
    sub = [G("STT", 1), G("Nguồn", 2), G("Số bài", 3), G("Tiêu đề", 4), G("A"), G("B"), G("C")]
    rows = [header, sub]
    posts = [("Nguồn X", "a"), ("Nguồn X", "c"), ("Nguồn X", "c"), ("Nguồn Y", "b"), ("Nguồn Y", "c")]
    for k, (src, mark) in enumerate(posts):
        count = "3" if src == "Nguồn X" else "2"
        rows.append([G(""), G(src, src), G(count, src + "n"), G(f"Bài {k + 1}"),
                     G("1" if mark == "a" else ""), G("1" if mark == "b" else ""), G("1" if mark == "c" else "")])
    rows.append([G("Tổng"), G(""), G("5"), G(""), G("1"), G("1"), G("3")])
    text = "# Bản tin\n\n" + render_table(rows)
    return [ParsedPage(page_number=1, text=text)]


def test_rows_marked_in_a_sub_column_are_listed_and_counted_completely():
    tables = extract_tables(_bulletin_page(), "d", "Bản tin")
    assert len(tables) == 1 and tables[0].columns[-1] == "Nhóm / C"
    assert tables[0].total_rows == [5]  # found by arithmetic, the word "Tổng" plays no part
    listed = run_query(tables, Q([0], "list", [C("C", "nonempty")], show=["Tiêu đề"]))
    assert [m.row[3] for m in listed.matches] == ["Bài 2", "Bài 3", "Bài 5"]
    counted = run_query(tables, Q([0], "count", [C("Nhóm / C", "nonempty")]))
    assert counted.value == 3  # equals the document's own total for that column


def test_sum_of_a_merged_column_counts_each_merge_once():
    tables = extract_tables(_bulletin_page(), "d", "Bản tin")
    total = run_query(tables, Q([0], "sum", target="Số bài"))
    assert total.value == 5  # 3 (Nguồn X, merged over 3 rows) + 2 (Nguồn Y): matches the totals row


def test_equal_figures_with_identical_long_notes_are_not_a_merge():
    note = "Có từ một bằng chứng tích cực trở lên thì cộng điểm; không bù trừ giữa các bằng chứng tiêu cực."
    md = "| Mã | Điểm | Ghi chú |\n| --- | --- | --- |\n" + "".join(
        f"| M{i} | {v} | {note} |\n" for i, v in enumerate((10, 10, 5, 5))) + "| Tổng |  30 |  |\n"
    tables = extract_tables([ParsedPage(page_number=1, text=md)], "d", "Tiêu chí")
    assert run_query(tables, Q([0], "sum", target="Điểm")).value == 30


def test_same_table_in_every_document_of_a_template_is_read():
    def pages(lv):
        return [ParsedPage(page_number=1, text=(
            "| Nhóm | Tên năng lực | Cấp độ |\n| --- | --- | --- |\n"
            f"| Chung | Đạo đức | {lv[0]} |\n| Quản lý | Tư duy chiến lược | {lv[1]} |\n"))]

    tables = []
    for name, lv in (("Vị trí A", (3, 4)), ("Vị trí B", (2, 4)), ("Vị trí C", (3, 1))):
        tables += extract_tables(pages(lv), name, name)
    r = run_query(tables, Q([0], "list", [C("Tên năng lực", "contains", "chiến lược"), C("Cấp độ", "=", "4")]))
    assert sorted(m.table.title for m in r.matches) == ["Vị trí A", "Vị trí B"]
    assert "Vị trí A:" in render_result(r)  # several documents: each row names its document


def test_small_figures_of_data_rows_are_not_totals():
    rows = [["Chung", "Đạo đức", "1"], ["Chung", "Tổ chức", "1"], ["Chung", "Giao tiếp", "2"]]
    assert total_rows(rows) == []  # 2 = 1 + 1, but the row is a data row like the others


def test_planner_sees_one_entry_per_template_and_its_plan_is_parsed():
    def pages():
        return [ParsedPage(page_number=1, text="| Tên năng lực | Cấp độ |\n| --- | --- |\n| X | 1 |\n")]

    tables = extract_tables(pages(), "a", "Vị trí A") + extract_tables(pages(), "b", "Vị trí B")
    prompt = planner_messages("Vị trí nào cần cấp độ 1?", tables)[1]["content"]
    assert prompt.count("[") == 1 and "Vị trí A, Vị trí B" in prompt
    plan = parse_plan('{"applicable": true, "tables": [0], "operation": "list", '
                      '"conditions": [{"column": "Cấp độ", "op": "=", "value": "1"}]}')
    assert plan.table_ids == [0] and plan.conditions[0].value == "1"
    assert parse_plan('{"applicable": false}') is None


# ---------------------------------------------------------------- chat route (scripted LLM, in-memory table store)
class MemoryTables:
    def __init__(self, records):
        self.records = records
        self.calls = []

    async def replace_document(self, tenant_id, doc_id, allowed_roles, tables):
        return len(tables)

    async def delete_document(self, tenant_id, doc_id):
        return 0

    async def list_tables(self, tenant_id, user_role="user", doc_ids=None, signatures=None, limit=500):
        self.calls.append((tuple(doc_ids or ()), tuple(signatures or ())))
        return [r.to_dict() for r in self.records
                if (not doc_ids or r.doc_id in doc_ids) and (not signatures or r.signature in signatures)][:limit]


def test_listing_question_is_answered_with_every_row_of_the_stored_table():
    import asyncio

    from solutions.rag.application.dtos import RagChatRequestDTO
    from solutions.rag.application.use_cases.chat_use_case import RagChatUseCase
    from test_rag_answer_pipeline import CORPUS, CorpusStore, Embedder, Repo, ScoreReranker, ScriptedLLM

    # Two documents of one template: the second is not among the retrieved passages at all.
    def page(rows):
        return [ParsedPage(page_number=1, text="| Mục | Nội dung | Mức |\n| --- | --- | --- |\n" + rows)]

    records = (extract_tables(page("| Nghỉ phép | Ngày phép năm | 12 |\n| Giờ làm | Thời gian | 8 |\n"), "doc_hr", "Quy chế A")
               + extract_tables(page("| Nghỉ phép | Ngày phép năm | 14 |\n"), "doc_other", "Quy chế B"))
    plan = ('{"applicable": true, "tables": [0], "operation": "list", '
            '"conditions": [{"column": "Mục", "op": "=", "value": "Nghỉ phép"}], "show": ["Mức"]}')
    llm = ScriptedLLM({"intent": "document_question", "standalone_query": "Liệt kê số ngày phép năm", "wants_list": True}, plan)
    store = MemoryTables(records)
    uc = RagChatUseCase(CorpusStore(), Embedder(), llm, Repo(), reranker_service=ScoreReranker(), table_store=store)
    resp = asyncio.run(uc.execute(RagChatRequestDTO(query="Liệt kê số ngày phép năm", similarity_threshold=0.65)))
    assert resp.intent == "QA_TABLE"
    assert "Quy chế A: 12" in resp.answer and "Quy chế B: 14" in resp.answer  # read beyond the retrieved document
    assert store.calls[0][0] == (CORPUS[0]["payload"]["doc_id"],) or "doc_hr" in store.calls[0][0]


def test_plan_selecting_nothing_falls_back_to_the_passage_routes():
    import asyncio

    from solutions.rag.application.dtos import RagChatRequestDTO
    from solutions.rag.application.use_cases.chat_use_case import RagChatUseCase
    from test_rag_answer_pipeline import CorpusStore, Embedder, Repo, ScoreReranker, ScriptedLLM

    records = extract_tables([ParsedPage(page_number=1, text="| Mục | Mức |\n| --- | --- |\n| Nghỉ phép | 12 |\n")], "doc_hr", "Quy chế A")
    plan = '{"applicable": true, "tables": [0], "operation": "list", "conditions": [{"column": "Mục", "op": "=", "value": "Không có"}]}'
    llm = ScriptedLLM({"intent": "document_question", "standalone_query": "Liệt kê ngày phép năm", "wants_list": True}, plan)
    uc = RagChatUseCase(CorpusStore(), Embedder(), llm, Repo(), reranker_service=ScoreReranker(), table_store=MemoryTables(records))
    resp = asyncio.run(uc.execute(RagChatRequestDTO(query="Liệt kê ngày phép năm", similarity_threshold=0.65)))
    assert resp.intent != "QA_TABLE"


def test_neighbouring_merges_with_equal_figures_are_counted_separately():
    md = ("| Nguồn | Số bài | Tiêu đề |\n| --- | --- | --- |\n"
          "| A | 2 | a1 |\n| A | 2 | a2 |\n| B | 2 | b1 |\n| B | 2 | b2 |\n| C | 1 | c1 |\n| Tổng | 5 |  |\n")
    tables = extract_tables([ParsedPage(page_number=1, text=md)], "d", "Bản tin")
    assert run_query(tables, Q([0], "sum", target="Số bài")).value == 5  # 2 (A) + 2 (B) + 1 (C)
