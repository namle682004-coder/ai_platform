"""
Fixes found by the acceptance suite: reworded refusals, refusal recovery on generic terms, the
structured-listing planner (no filter, enumerated groups, disagreement with the best passage).
"""

from types import SimpleNamespace

from solutions.rag.application.components.answer_postprocessor import is_llm_refusal, sanitize_answer
from solutions.rag.application.components.answer_postprocessor import SanitizeContext
from solutions.rag.application.components.answer_verifier import specific_focus_terms
from solutions.rag.application.components.table_rows import TablePlan, mentioned_in, refine_plan
from solutions.rag.application.use_cases.chat_use_case import RagChatUseCase


def _chunk(text, heading=""):
    return {"payload": {"text": text, "heading": heading, "doc_id": "d", "chunk_index": 0}}


def test_reworded_no_information_answers_are_refusals():
    assert is_llm_refusal("Tài liệu không cung cấp thông tin về số tiết học AI mỗi tuần cho lớp 10. [1]")
    assert is_llm_refusal("**Tài liệu nội bộ không có thông tin về khi nào AI trở thành môn thi.**")
    assert is_llm_refusal("Văn bản chưa đề cập đến chứng chỉ của giáo viên [1].")
    # An identifier is evidence; an ordinary answer is not a refusal.
    assert not is_llm_refusal("Tài liệu không nêu riêng lớp 12, nội dung này ở 11.C3.MR4.")
    assert not is_llm_refusal("RAG được học ở lớp 11 (11.C3.MR4) [1].")
    # The whole answer: a no-information sentence followed only by a marker is refused ...
    _, _, refused = sanitize_answer("Tài liệu không cung cấp thông tin về số tiết. [1]", SanitizeContext())
    assert refused
    # ... while an evidenced continuation is kept as a partial answer.
    text, _, refused = sanitize_answer(
        "Tài liệu không có thông tin đúng như câu hỏi. Mạng nơ-ron được học ở lớp 11 theo 11.C5.1 [1].",
        SanitizeContext(),
    )
    assert not refused and "11.C5.1" in text


def test_specific_focus_terms_ignore_scope_title_and_ubiquitous_words():
    chunks = [_chunk("AI lớp 10 nội dung A1"), _chunk("AI lớp 10 nội dung A2"), _chunk("AI lớp 11 RAG"),
              _chunk("AI lớp 12 Teachable Machine")]
    titles = ["KHUNG NỘI DUNG GIÁO DỤC TRÍ TUỆ NHÂN TẠO CHO HỌC SINH PHỔ THÔNG"]
    assert specific_focus_terms(["AI"], [], titles, chunks) == []  # in every passage
    assert specific_focus_terms(["học sinh"], [], titles, chunks) == []  # words of the title
    assert specific_focus_terms(["lớp 10"], ["lớp 10"], titles, chunks) == []  # a scope word
    assert specific_focus_terms(["RAG", "chứng chỉ"], [], titles, chunks) == ["RAG", "chứng chỉ"]


def _plan(**kw):
    base = dict(applicable=True, sections=[], groups=[], terms=[], identifier_regex=None, group_by="group",
                level="items")
    base.update(kw)
    return TablePlan(**base)


def test_planner_groups_are_kept_only_when_the_question_names_them():
    assert mentioned_in("A2. AI vì sự tiến bộ của con người", "Chủ đề A2 gồm gì?")
    assert not mentioned_in("A1. Tính chủ động của con người", "Lớp 10 học những chủ đề nào?")
    assert not mentioned_in("B3. Nguyên tắc đạo đức và trách nhiệm xã hội",
                            "Nguyên tắc đạo đức khi thiết kế AI gồm những gì?")
    assert mentioned_in("B3. Nguyên tắc đạo đức và trách nhiệm xã hội",
                        "Trách nhiệm xã hội và nguyên tắc đạo đức học gì?")

    p = refine_plan(_plan(sections=["LỚP 10"], groups=["A1. Tính chủ động", "A2. AI vì sự tiến bộ"], level="groups"),
                    "Lớp 10 học những chủ đề nào?")
    assert p.groups == [] and p.level == "groups"  # all topics of the class, not the three the planner recalled
    p = refine_plan(_plan(groups=["C5", "D1"], level="groups"), "Tên chính xác của chủ đề C5 và D1 là gì?")
    assert p.groups == ["C5", "D1"] and p.level == "groups"  # bare codes the user typed are kept


def test_terms_match_items_not_group_names():
    from solutions.rag.application.components.table_rows import apply_plan, build_schema, parse_table_rows, row_items

    table = _chunk(
        "| Chủ đề | Nội dung | Yêu cầu cần đạt |\n| --- | --- | --- |\n"
        "| A2. AI vì sự tiến bộ | Nguyên tắc đạo đức khi thiết kế AI | 12.A2.1. Trình bày được: an toàn, công bằng. |\n"
        "| B3. Nguyên tắc đạo đức và trách nhiệm xã hội | Trách nhiệm | 12.B3.1. Trình bày được quyền. |", "LỚP 12")
    items = row_items(parse_table_rows([table]))
    picked = apply_plan(items, _plan(terms=["nguyên tắc đạo đức"]), build_schema(items), 50)
    assert [it.identifier for it in picked] == ["12.A2.1"]


def test_structured_listing_rejections():
    item = lambda i: SimpleNamespace(identifier=i)  # noqa: E731
    reject = RagChatUseCase._structured_reject_reason
    many = [item("10.A1.1"), item("10.A1.2"), item("10.A2.1")]
    assert reject(_plan(), many, True, None) == "no filter"
    assert reject(_plan(level="groups"), many, True, None) == ""  # listing every group name is a real answer
    assert reject(_plan(terms=["RAG"]), [item("11.C3.MR4")], True, None) == "term lookup"
    best = _chunk("| A2 | Nguyên tắc đạo đức | 12.A2.1. Trình bày được …")
    b3 = [item("10.B3.1"), item("11.B3.MR1"), item("12.B3.1")]
    assert reject(_plan(groups=["B3"]), b3, True, best) == "disagrees with the best passage"
    assert reject(_plan(sections=["LỚP 10"]), many, True, _chunk("10.A1.1. Thực hành …")) == ""


def test_mostly_unaccented_queries():
    from solutions.rag.application.components.lexical_evidence import mostly_unaccented

    assert mostly_unaccented("mang no ron nhan tao hoc lop may")
    assert mostly_unaccented("quyen của nguoi dung du lieu")  # one accented word does not make it readable
    assert not mostly_unaccented("Quyền của người dùng dữ liệu")
    assert not mostly_unaccented("RAG?")


def test_items_after_an_ellipsis_are_items_not_examples():
    from solutions.rag.application.components.answer_verifier import build_grounding
    from solutions.rag.application.components.table_rows import parse_table_rows, row_items

    table = _chunk(
        "| Chủ đề | Nội dung | Yêu cầu cần đạt |\n| --- | --- | --- |\n"
        "| C3. Công nghệ AI | Tùy chỉnh | 11.C3.MR3. Xác định được phương pháp (RAG), … 11.C3.MR4. Trình bày được "
        "cách hoạt động của RAG. |", "LỚP 11")
    convention = _chunk("- 6.A1.MR1: Yêu cầu cần đạt mở rộng thứ nhất, lớp 6.", "Quy ước")
    convention["payload"]["chunk_index"] = 1
    ids = [it.identifier for it in row_items(parse_table_rows([table]))]
    assert ids == ["11.C3.MR3", "11.C3.MR4"]
    g = build_grounding([table], [table, convention], allow_examples=False, language_guard=False)
    assert "11.C3.MR4" not in g.example_identifiers and "6.A1.MR1" in g.example_identifiers
    assert g.sentence_problem("RAG ở lớp 11, mã 11.C3.MR4.") is None


def test_content_terms_list_items_not_group_names():
    p = refine_plan(_plan(groups=["B3"], terms=["Nguyên tắc đạo đức"], level="groups"),
                    "Nguyên tắc đạo đức khi thiết kế AI gồm những gì?")
    assert p.groups == [] and p.level == "items"


def test_a_refusal_followed_by_a_quote_of_the_passages_is_a_partial_answer():
    passage = "11.C3.MR4. Trình bày được cách hoạt động của kĩ thuật sinh nội dung tăng cường bằng truy xuất (RAG)."
    raw = ("Hiện tài liệu nội bộ chưa có thông tin để trả lời câu hỏi này. Tài liệu chỉ đề cập việc học kĩ thuật "
           "sinh nội dung tăng cường bằng truy xuất ở lớp 11, lớp 10 không có yêu cầu này.")
    text, _, refused = sanitize_answer(raw, SanitizeContext(evidence_text=passage))
    assert not refused and "lớp 11" in text
    _, _, refused = sanitize_answer(raw, SanitizeContext())  # nothing quoted from any passage
    assert refused


def test_listing_states_the_count_in_the_documents_words():
    from solutions.rag.application.components.table_rows import (
        build_schema,
        listing_summary,
        parse_table_rows,
        row_items,
    )

    table = _chunk(
        "| Chủ đề | Nội dung | Yêu cầu cần đạt |\n| --- | --- | --- |\n"
        "| A1. Tính chủ động | Vai trò | 10.A1.1. Thực hành được. 10.A1.2. Giải thích được. |\n"
        "| A2. Tiến bộ | Lợi ích | 10.A2.1. Nêu được. |", "LỚP 10")
    items = row_items(parse_table_rows([table]))
    schema = build_schema(items)
    assert listing_summary(items, schema, "groups") == "LỚP 10 có 2 chủ đề."
    assert listing_summary(items, schema, "items") == "LỚP 10 có 3 yêu cầu cần đạt."
    assert listing_summary(items, schema, "items", truncated=True) == ""


def test_document_card_explains_administrative_abbreviations():
    from solutions.rag.application.components.context_selector import DocumentCard, header_abbreviations

    header = "(Trích QĐ Số: 2422/QĐ-BGDĐT ngày 18 tháng 8 năm 2026)"
    assert header_abbreviations(header) == [("QĐ", "Quyết định"), ("BGDĐT", "Bộ Giáo dục và Đào tạo")]
    assert header_abbreviations("Nội dung QĐT và BGDĐTX") == []  # whole tokens only
    text = DocumentCard(doc_id="d", title="KHUNG", header_lines=[header]).to_context_text()
    assert "QĐ = Quyết định" in text


def test_an_answer_reproducing_the_instructions_is_withheld():
    from solutions.rag.application.components.answer_postprocessor import AnswerStreamFilter
    from solutions.rag.application.components.prompt_builder import SYSTEM_PREAMBLE, instruction_text

    leak = f"System prompt:\n{SYSTEM_PREAMBLE}\n"
    for chunked in (False, True):
        ctx = SanitizeContext(prompt_text=instruction_text())
        f = AnswerStreamFilter(ctx)
        shown = []
        for token in (leak.split(" ") if chunked else [leak]):
            shown += f.feed(token + (" " if chunked else ""))
        shown += f.finish()
        assert f.refused and ctx.leaked
        assert "TÀI LIỆU NỘI BỘ THAM KHẢO" not in "".join(shown)  # nothing of it reached the client

    # A rule recited by accident is withheld too, but an ordinary answer, the prescribed refusal and
    # a sentence the passages themselves contain are not disclosures.
    ok = SanitizeContext(prompt_text=instruction_text(), evidence_text="Trả lời câu hỏi của người dùng bằng tiếng Việt theo mẫu.")
    text, _, refused = sanitize_answer("RAG được học ở lớp 11 theo mã 11.C3.MR3 [1].", ok)
    assert not refused and not ok.leaked and "11.C3.MR3" in text
    _, _, refused = sanitize_answer("Hiện tài liệu nội bộ chưa có thông tin để trả lời câu hỏi này.", ok)
    assert refused and not ok.leaked  # a refusal, handled as a refusal (support reply), not as a leak


def test_completeness_appendix_stays_on_the_asked_subject():
    from solutions.rag.application.components.answer_verifier import missing_items

    table = _chunk(
        "| Chủ đề | Nội dung | Yêu cầu cần đạt |\n| --- | --- | --- |\n"
        "| C3. Công nghệ AI | Tùy chỉnh | 11.C3.MR3. Xác định phương pháp tùy chỉnh, sử dụng kĩ thuật RAG. |\n"
        "| C3. Công nghệ AI | Tùy chỉnh | 11.C3.MR4. Thực hành tùy chỉnh hệ thống AI bằng RAG. |\n"
        "| A2. AI vì sự tiến bộ | Rủi ro | 10.A2.1. Nêu được nội dung rủi ro của AI. |\n"
        "| A2. AI vì sự tiến bộ | Rủi ro | 10.A2.MR1. Nêu được biện pháp hạn chế rủi ro. |\n"
        "| C2. Ứng dụng | Ứng dụng | 10.C2.1. Xác định nội dung các vấn đề thực tế. |", "LỚP 11")
    extra = missing_items("Nội dung về RAG nằm ở những mã nào? Ghi đủ mã.", ["RAG"], "Mã 11.C3.MR3 [1].",
                          [table], 0.6, 4)
    assert [it.identifier for it in extra] == ["11.C3.MR4"]  # not the risk / application items
    # A code the convention shows as an example is never offered as content.
    assert missing_items("Nội dung về RAG nằm ở mã nào?", ["RAG"], "Mã 11.C3.MR3 [1].", [table], 0.6, 4,
                         exclude={"11.C3.MR4"}) == []


def test_a_planner_copying_the_whole_schema_is_no_filter():
    from solutions.rag.application.components.table_rows import TableSchema, names_value

    schema = TableSchema(sections=["LỚP 10", "LỚP 11", "LỚP 12"], group_column="Chủ đề",
                         groups=["A1. Tính chủ động", "C3. Công nghệ AI"], sample_identifiers=["10.A1.1"])
    q = "Cho tôi các bước cụ thể để đặt prompt theo khung nội dung."
    p = refine_plan(_plan(sections=list(schema.sections), level="groups"), q, schema)
    assert p.sections == [] and not p.has_filter
    item = lambda i: SimpleNamespace(identifier=i)  # noqa: E731
    many = [item("10.A1.1"), item("11.C3.1"), item("12.C3.1")]
    assert RagChatUseCase._structured_reject_reason(p, many, True, None, schema, q) == "groups not asked"
    # Asking for the groups themselves, or naming a section, is a real listing.
    assert RagChatUseCase._structured_reject_reason(
        _plan(level="groups"), many, True, None, schema, "Khung có những chủ đề nào?") == ""
    p = refine_plan(_plan(sections=list(schema.sections), level="groups"), "So sánh lớp 10, lớp 11 và lớp 12", schema)
    assert p.sections == list(schema.sections)
    assert names_value("Chủ đề", "Lớp 12 có bao nhiêu chủ đề?") and not names_value("Chủ đề", q)


def test_weak_reranking_keeps_the_documents_the_search_points_to():
    from solutions.rag.application.use_cases.chat_use_case import leading_documents

    def cand(doc):
        return {"payload": {"doc_id": doc, "text": "", "chunk_index": 0}}

    results = [cand("khung")] * 6 + [cand("plan"), cand("khung"), cand("plan"), cand("news")]
    assert leading_documents(results) == {"khung"}
    assert leading_documents([cand("khung")] * 5) == set()  # one document: nothing to choose
    assert leading_documents([cand("a"), cand("b"), cand("a"), cand("b")]) == {"a", "b"}


def test_an_answer_that_only_states_absence_is_a_refusal():
    from solutions.rag.application.components.answer_postprocessor import has_substantive_content

    assert not has_substantive_content("Tài liệu không có thông tin đúng như câu hỏi đặt ra.")
    assert not has_substantive_content("[1]")
    assert not has_substantive_content(
        "Tài liệu không có thông tin đúng như câu hỏi đặt ra. Tài liệu chỉ đề cập đến các yêu cầu cần đạt của "
        "học sinh lớp 11 và 12, nhưng không có thông tin về cách đánh giá, chấm điểm học sinh [1].")
    assert not has_substantive_content(
        "Tài liệu chỉ đề cập đến nội dung giáo dục AI ở các lớp 10 và 11, không có thông tin về chương trình AI tổng thể.")
    # Short answers are answers.
    assert has_substantive_content("11.C3.MR4 [1]")
    assert has_substantive_content("Có. [1]")
    assert has_substantive_content(
        "Tài liệu không có thông tin đúng như câu hỏi đặt ra. Mạng nơ-ron được học ở lớp 11 theo 11.C5.1 [1].")

    # Streamed: an absence remark after a refusal opening, even citing a passage, ends as a refusal.
    _, _, refused = sanitize_answer(
        "Tài liệu không cung cấp thông tin về cách chấm điểm. Tài liệu chỉ đề cập đến yêu cầu cần đạt của các "
        "lớp, nhưng không có thông tin về đánh giá [1].", SanitizeContext())
    assert refused


def test_only_codes_shaped_like_the_items_are_convention_examples():
    from solutions.rag.application.components.answer_verifier import build_grounding, identifier_shape

    assert identifier_shape("10.A1.MR2") == identifier_shape("6.B3.MR1") == "9.A9.AA9"
    assert identifier_shape("2422/QĐ-BGDĐT") == "9/AA-AAAAA"
    header = {"payload": {"text": "(Trích QĐ Số: 2422/QĐ-BGDĐT)\nQuy ước mã hoá, ví dụ: 6.A1.2 là yêu cầu thứ hai.",
                          "heading": "", "doc_id": "d", "chunk_index": 0}}
    table = {"payload": {"text": "| Chủ đề | Nội dung | Yêu cầu cần đạt |\n| --- | --- | --- |\n"
                                 "| A1. Tính chủ động | Con người | 10.A1.1. Thực hành. 10.A1.2. Nêu được. |",
                         "heading": "LỚP 10", "doc_id": "d", "chunk_index": 1}}
    g = build_grounding([header, table], [header, table], allow_examples=False, language_guard=False)
    assert "6.A1.2" in g.example_identifiers           # illustrates the item numbering
    assert "2422/QĐ-BGDĐT" not in g.example_identifiers  # the decision the document is issued under


# ---------------------------------------------------------------- listing / counting over coded tables
def _khung_items():
    from solutions.rag.application.components.table_rows import build_schema, parse_table_rows, row_items

    head = "| Chủ đề | Nội dung | Yêu cầu cần đạt |\n| --- | --- | --- |\n"
    chunks = [
        {"payload": {"doc_id": "d", "chunk_index": 1, "heading": "LỚP 10", "text": head +
                     "| A2. AI vì sự tiến bộ | Rủi ro | 10.A2.1. Nêu rủi ro. 10.A2.MR1. Nêu biện pháp. |\n"
                     "| C2. Ứng dụng AI | Ứng dụng | 10.C2.1. Xác định vấn đề. 10.C2.MR1. Sử dụng công cụ. |\n"
                     "| C3. Công nghệ AI | Prompt | 10.C3.1. Mô tả prompt. 10.C3.2. Thực hành prompt. |"}},
        {"payload": {"doc_id": "d", "chunk_index": 2, "heading": "LỚP 11", "text": head +
                     "| C3. Công nghệ AI | Tùy chỉnh | 11.C3.MR3. RAG. 11.C3.MR4. Thực hành RAG. |\n"
                     "| C5. Kĩ thuật và thuật toán AI | Mạng nơ-ron | 11.C5.1. Nêu ứng dụng. |"}},
    ]
    items = row_items(parse_table_rows(chunks))
    return items, build_schema(items)


def test_listing_filters_come_from_the_question_not_the_planner_guess():
    from solutions.rag.application.components.table_rows import question_filters, reconcile_plan

    items, schema = _khung_items()
    q = "Liệt kê mã mở rộng (MR) của lớp 10."
    wanted = question_filters(q, items, schema)
    assert wanted.sections == ["LỚP 10"] and wanted.segment == "MR"
    # The planner's regex of the wrong shape and a term absent from the items are overridden / dropped.
    import re
    p, picked = reconcile_plan(_plan(terms=["MR"], identifier_regex=re.compile(r"10\.A[123]\.MR\d+")), wanted,
                               items, schema, 80)
    assert [it.identifier for it in picked] == ["10.A2.MR1", "10.C2.MR1"]

    wanted = question_filters("Liệt kê các mã thuộc chủ đề C của lớp 10.", items, schema)
    assert wanted.sections == ["LỚP 10"] and all(g[0] == "C" for g in wanted.groups)
    _, picked = reconcile_plan(_plan(identifier_regex=re.compile(r"^10\.C\d+$")), wanted, items, schema, 80)
    assert [it.identifier for it in picked] == ["10.C2.1", "10.C2.MR1", "10.C3.1", "10.C3.2"]

    # "đủ 22 mã": the section alone is the filter; the count is the user's claim, not a filter.
    wanted = question_filters("Liệt kê đầy đủ, lớp 10 có 22 mã", items, schema)
    _, picked = reconcile_plan(_plan(), wanted, items, schema, 80)
    assert len(picked) == 6 and all(it.identifier.startswith("10.") for it in picked)
    # Ordinary capitalised words are not filters.
    assert not question_filters("RAG và AI agent học ở lớp nào?", items, schema).segment


def test_count_and_list_questions_are_answered_in_code():
    from solutions.rag.application.components.table_rows import listing_summary, question_filters, reconcile_plan

    items, schema = _khung_items()
    wanted = question_filters("Lớp 10 có bao nhiêu yêu cầu cần đạt?", items, schema)
    _, picked = reconcile_plan(_plan(), wanted, items, schema, 80)
    assert listing_summary(picked, schema, "items") == "LỚP 10 có 6 yêu cầu cần đạt."


# ---------------------------------------------------------------- figures over many small tables
def _bulletin_chunks():
    head = "| Nguồn MXH | Ngày đăng | Lượt xem/like | Lượt bình luận | Lượt chia sẻ |\n| --- | --- | --- | --- | --- |\n"

    def c(i, path, body):
        return {"payload": {"doc_id": "b", "chunk_index": i, "heading": path.split(">")[-1].strip(),
                            "text": f"[Ngữ cảnh: {path}]\n\n{body}"}}

    return [
        c(1, "MỤC 1 > Shipper trả lại tiền", head + "| Tin tức 24h | 02/11 | 55 | 3 | 1 |\n| Hóng Biến 47 | 02/11 | 3,5k | 250 | 16 |"),
        c(2, "MỤC 2 > Học sinh đánh nhau", head + "| Mi Nguyễn | 02/11 | 1,1k | 85 | 4 |"),
        c(3, "MỤC 3 > Khởi tố 2 đối tượng", head + "| Công an tỉnh | 02/11 | 4,2K | 351 | 327 |\n| Tin tức 24h | 02/11 | 40 | 1 | 0 |"),
        c(4, "PHẦN C: THỐNG KÊ NGUỒN",
          "| STT | Nguồn MXH | Loại hình | Số tin/ bài | Tiêu đề |\n| --- | --- | --- | --- | --- |\n"
          "|  | Tin tức 24h | FB | 2 | Shipper trả lại tiền |\n|  | Tin tức 24h | FB | 2 | Khởi tố 2 đối tượng |\n"
          "|  | Hóng Biến 47 | FB | 1 | Shipper trả lại tiền |\n|  | Công an tỉnh | FB | 1 | Khởi tố 2 đối tượng |"),
    ]


def test_same_header_tables_are_one_family_and_cover_every_article():
    from solutions.rag.application.components.numeric_tables import (
        NumericPlan, compute_answer, expand_to_families, parse_numeric_tables, schema_text, table_families,
    )

    tables = parse_numeric_tables(_bulletin_chunks())
    fams = table_families(tables)
    assert sorted(len(f) for f in fams) == [1, 3]
    assert schema_text(tables).count('"numeric_columns"') == 2  # one schema entry per family
    # The planner named one article's table; the question names none: every article is compared.
    first = next(t for t in tables if "Shipper" in t.title)
    q = "Bài viết nào có nhiều lượt bình luận nhất?"
    chosen = expand_to_families([first], tables, q)
    assert len(chosen) == 3
    body, _ = compute_answer(NumericPlan(tables=chosen, column="Lượt bình luận", operation="max", unit="table",
                                         table_reduce="sum", rows=[]))
    assert "Khởi tố 2 đối tượng" in body.split("\n")[0] and "352" in body.split("\n")[0]
    # Naming an article keeps the planner's choice.
    assert len(expand_to_families([first], tables, "Ở bài shipper trả lại tiền, nguồn nào nhiều bình luận nhất?")) == 1


def test_a_label_repeated_with_the_same_figure_is_listed_once():
    from solutions.rag.application.components.numeric_tables import NumericPlan, compute_answer, parse_numeric_tables

    stats = next(t for t in parse_numeric_tables(_bulletin_chunks()) if "THỐNG KÊ" in t.title)
    body, _ = compute_answer(NumericPlan(tables=[stats], column="Số tin/ bài", operation="sort_desc", unit="row",
                                         table_reduce="sum", rows=[]), max_rows=60)
    rows = [line for line in body.splitlines() if line.startswith("| ") and "---" not in line][1:]
    assert rows == ["| Tin tức 24h | 2 |", "| Hóng Biến 47 | 1 |", "| Công an tỉnh | 1 |"]


def test_row_and_column_naming():
    from solutions.rag.application.components.numeric_tables import column_named, label_named

    q = "Liệt kê toàn bộ các nguồn MXH trong Phần C kèm số lượng bài viết của từng nguồn."
    assert column_named("Số tin/ bài", q) and not column_named("Lượt chia sẻ", q)
    assert column_named("Lượt xem/like", "Nguồn nào có lượt xem/like cao nhất?")
    assert not label_named("Báo Đắk Lắk", q)  # a recalled row label is not a filter the user asked for
    assert label_named("Hóng Biến 47 Fanpage", "Hóng Biến 47 có bao nhiêu bài?")


def test_only_what_the_table_lists_is_counted_in_code():
    from solutions.rag.application.components.table_rows import counts_column

    assert counts_column("yêu cầu", "Yêu cầu cần đạt") and counts_column("chủ đề", "Chủ đề")
    assert not counts_column("tiết", "Yêu cầu cần đạt")  # "bao nhiêu tiết AI mỗi tuần" is not a count of items
    assert not counts_column("", "Chủ đề")
