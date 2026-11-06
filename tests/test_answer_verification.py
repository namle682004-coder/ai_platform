"""
Tests for structured listing (table rows + self-query plan), post-generation verification (language,
identifier/number grounding, examples, completeness), refusal recovery, policy check and conversation
memory. Neutral HR sample corpus (shared with test_rag_answer_pipeline).
"""

import asyncio
import json
from typing import Any, AsyncGenerator, Dict, List, Tuple

from solutions.rag.application.components.answer_postprocessor import AnswerStreamFilter, SanitizeContext, sanitize_answer
from solutions.rag.application.components.answer_verifier import (
    GroundingContext,
    build_grounding,
    extractive_answer,
    is_english_text,
    missing_items,
    split_sentences,
)
from solutions.rag.application.components.prompt_builder import REFUSAL_MESSAGE
from solutions.rag.application.components.query_analyzer import ANALYZER_MARKER, QueryAnalyzer
from solutions.rag.application.components.table_rows import (
    PLANNER_MARKER,
    apply_plan,
    build_schema,
    parse_plan,
    parse_table_rows,
    render_items,
    row_items,
)
from solutions.rag.application.dtos import RagChatRequestDTO
from solutions.rag.application.use_cases.chat_use_case import RagChatUseCase, _enrich_history
from tests.test_rag_answer_pipeline import CORPUS, TITLE, Embedder, Repo, ScoreReranker, _chunk

EXAMPLE_CHUNK = _chunk(5, "Quy ước", "Mỗi mục có mã dạng [Phòng].[Nhóm].[Số]. Ví dụ: HR.Z9.7 là mục thứ bảy của nhóm Z9.")


# ---------------------------------------------------------------- table rows
def test_table_rows_are_parsed_and_cells_split_into_items():
    items = row_items(parse_table_rows(CORPUS))
    ids = [it.identifier for it in items]
    assert ids == ["HR.A1.1", "HR.A2.1", "HR.A2.MR1", "HR.B1.1", "HR.B2.1"]
    phep = next(it for it in items if it.identifier == "HR.A2.MR1")
    assert phep.text.startswith("HR.A2.MR1.") and phep.row.section == "CHƯƠNG I"
    assert dict(phep.context_cells())["Mục"] == "Nghỉ phép"


def test_plan_filters_by_section_group_and_identifier_pattern():
    items = row_items(parse_table_rows(CORPUS))
    schema = build_schema(items)
    assert schema.group_column == "Mục" and schema.sections == ["CHƯƠNG I", "CHƯƠNG II"]
    plan = parse_plan(json.dumps({"applicable": True, "sections": ["CHƯƠNG I"], "identifier_regex": "MR\\d"}), schema)
    assert [it.identifier for it in apply_plan(items, plan, schema, 50)] == ["HR.A2.MR1"]
    plan = parse_plan('{"applicable": true, "level": "groups", "sections": ["CHƯƠNG II"]}', schema)
    rendered = render_items(apply_plan(items, plan, schema, 50), schema, plan.group_by, "", level=plan.level)
    assert rendered.splitlines() == ["- Làm việc từ xa (HR.B1.1)", "- Thiết bị (HR.B2.1)"]
    # Values that are not in the schema are ignored instead of filtering everything out.
    plan = parse_plan('{"applicable": true, "sections": ["CHƯƠNG IX"], "terms": ["laptop"]}', schema)
    assert [it.identifier for it in apply_plan(items, plan, schema, 50)] == ["HR.B2.1"]


# ---------------------------------------------------------------- verification
def test_sentences_are_not_cut_after_an_item_label():
    parts = split_sentences("- HR.A2.1. Mỗi năm có 12 ngày phép. Thêm câu thứ hai. ")
    assert parts[0].startswith("- HR.A2.1. Mỗi năm") and len(parts) == 2


def test_english_sentences_are_detected_but_tool_lists_are_not():
    assert is_english_text("Specifically, the requirement is that students should be able to explain it.")
    assert not is_english_text("Teachable Machine, TensorFlow.js, MIT App Inventor")
    assert not is_english_text("Mỗi năm có 12 ngày phép theo quy chế.")


def test_grounding_drops_invented_identifiers_examples_and_numbers():
    g = build_grounding(CORPUS, CORPUS + [EXAMPLE_CHUNK], allow_examples=False, language_guard=True)
    assert "HR.Z9.7" in g.example_identifiers
    assert g.sentence_problem("Phép năm ở HR.A2.1.") is None
    assert g.sentence_problem("Mục HR.A9.4 quy định thêm.").startswith("identifier")
    assert g.sentence_problem("Theo HR.Z9.7 thì có thêm mục.").startswith("example")
    assert g.sentence_problem("Quy chế ban hành năm 2019.").startswith("number")
    assert g.sentence_problem("Quy chế ban hành năm 2026.") is None


def test_stream_filter_applies_grounding_sentence_by_sentence():
    g = build_grounding(CORPUS, CORPUS, allow_examples=False, language_guard=True)
    ctx = SanitizeContext(titles=[TITLE], valid_indices={1, 2}, grounding=g)
    raw = (
        "Mỗi năm có 12 ngày phép theo HR.A2.1 [1]. Specifically, the requirement is that staff should rest. "
        "Ngoài ra còn mục HR.A2.MR9 về nghỉ bù."
    )
    f = AnswerStreamFilter(ctx)
    emitted = []
    for i in range(0, len(raw), 6):
        emitted += f.feed(raw[i:i + 6])
    emitted += f.finish()
    text = "".join(emitted)
    assert "HR.A2.1 [1]" in text and "Specifically" not in text and "HR.A2.MR9" not in text
    assert {reason.split(":")[0] for reason, _ in f.dropped} == {"language", "identifier"}


def test_bracketed_identifier_and_echoed_context_header_are_repaired():
    raw = "Mục nằm ở [11].A2.MR1 (Tài liệu: Quy chế Làm việc Nội bộ, Trang: 1, Mục: CHƯƠNG I) [1]."
    text, _, _ = sanitize_answer(raw, SanitizeContext(titles=[TITLE], valid_indices={1, 11}))
    assert "11.A2.MR1" in text and "Tài liệu:" not in text and "[1]" in text


def test_missing_relevant_items_are_listed():
    answer = "Phép năm: HR.A2.1. Mỗi năm có 12 ngày phép [1]."
    extra = missing_items("Quy định về phép năm và phép thâm niên?", ["phép"], answer, CORPUS, 0.6, 4)
    assert [it.identifier for it in extra] == ["HR.A2.MR1"]
    # Unrelated answers get nothing grafted on.
    assert missing_items("Quy định về phép?", ["phép"], "Không liên quan.", CORPUS, 0.6, 4) == []


def test_extractive_answer_quotes_the_items_holding_the_focus():
    text = extractive_answer(["laptop"], CORPUS)
    assert "HR.B2.1. Nhân viên được cấp laptop." in text and "CHƯƠNG II" in text


# ---------------------------------------------------------------- analyzer
def test_analyzer_reads_focus_scope_format_and_keeps_reply_tails():
    qa = QueryAnalyzer()
    parsed = qa.parse(
        '{"intent": "document_question", "standalone_query": "x", "focus": ["phép thâm niên"], "scope": ["chương II"], '
        '"format": "table", "wants_location": true}', "x", [], 1.0,
    )
    assert parsed.focus_terms == ["phép thâm niên"] and parsed.scope_terms == ["chương II"]
    assert parsed.answer_format == "table" and parsed.wants_location
    long_reply = "Hiện chưa có thông tin. " + "x" * 600 + " Nếu muốn được gọi lại, bạn có thể nhắn số điện thoại."
    msgs = qa.build_messages("Tôi không muốn để lại số.", [
        {"role": "user", "content": "Câu hỏi?"},
        {"role": "assistant", "content": long_reply, "intent": "REFUSAL", "asked_contact": True},
    ])
    assert "nhắn số điện thoại" in msgs[1]["content"] and "đã mời để lại số điện thoại" in msgs[1]["content"]


def test_client_history_is_enriched_with_stored_turn_memory():
    history = [{"role": "user", "content": "Phép năm?"}, {"role": "assistant", "content": "12 ngày (HR.A2.1)."}]
    stored = [
        {"role": "user", "content": "Phép năm?", "focus": ["phép năm"], "scope": ["chương I"]},
        {"role": "assistant", "content": "12 ngày (HR.A2.1).", "identifiers": ["HR.A2.1"]},
    ]
    out = _enrich_history(history, stored)
    assert out[0]["focus"] == ["phép năm"] and out[1]["identifiers"] == ["HR.A2.1"]


# ---------------------------------------------------------------- use case
class RoutingLLM:
    """Answers analyzer, planner, policy and generation calls from a script."""

    def __init__(self, analysis: Dict[str, Any], answers: List[str], plan: Dict[str, Any] = None, policy: Dict[str, Any] = None):
        self.analysis, self.answers, self.plan, self.policy = analysis, list(answers), plan, policy
        self.generation_calls = 0

    async def generate(self, messages, model, temperature=0.2, max_tokens=1024, authorization=None) -> Tuple[str, int, int]:
        system = messages[0]["content"]
        if PLANNER_MARKER in system:
            return json.dumps(self.plan or {"applicable": False}, ensure_ascii=False), 1, 1
        if ANALYZER_MARKER in system and "chính sách" in system and "in_policy" in system:
            return json.dumps(self.policy or {"in_policy": False}, ensure_ascii=False), 1, 1
        if ANALYZER_MARKER in system:
            if "Viết lại câu hỏi tra cứu" in system:
                return '{"queries": []}', 1, 1
            return json.dumps(self.analysis, ensure_ascii=False), 1, 1
        self.generation_calls += 1
        return (self.answers.pop(0) if self.answers else REFUSAL_MESSAGE), 1, 1

    async def stream_generate(self, messages, model, temperature=0.2, max_tokens=1024, authorization=None) -> AsyncGenerator[str, None]:
        text, _, _ = await self.generate(messages, model, temperature, max_tokens, authorization)
        for i in range(0, len(text), 5):
            yield text[i:i + 5]


class TableStore:
    async def search(self, **kwargs) -> List[Dict[str, Any]]:
        return [dict(c) for c in CORPUS]

    async def fetch_document_chunks(self, doc_id, tenant_id, user_role="user", limit=300):
        return [dict(c) for c in CORPUS + [EXAMPLE_CHUNK] if c["payload"]["doc_id"] == doc_id]


def _uc(llm) -> Tuple[RagChatUseCase, Repo]:
    repo = Repo()
    return RagChatUseCase(TableStore(), Embedder(), llm, repo, reranker_service=ScoreReranker()), repo


def test_listing_question_is_answered_from_table_rows():
    llm = RoutingLLM(
        {"intent": "document_question", "standalone_query": "Chương II gồm những mục nào?", "wants_list": True},
        answers=[], plan={"applicable": True, "level": "items", "sections": ["CHƯƠNG II"]},
    )
    uc, _ = _uc(llm)
    resp = asyncio.run(uc.execute(RagChatRequestDTO(query="Chương II gồm những mục nào?", similarity_threshold=0.0)))
    assert resp.intent == "QA_STRUCTURED" and llm.generation_calls == 0
    assert "HR.B1.1. Tối đa 2 ngày mỗi tuần." in resp.answer and "HR.B2.1." in resp.answer and "HR.A1.1" not in resp.answer
    assert resp.citations


def test_refusal_over_passages_containing_the_focus_is_recovered():
    llm = RoutingLLM(
        {"intent": "document_question", "standalone_query": "Laptop được cấp thế nào?", "focus": ["laptop"]},
        answers=[REFUSAL_MESSAGE, REFUSAL_MESSAGE],
    )
    uc, repo = _uc(llm)
    resp = asyncio.run(uc.execute(RagChatRequestDTO(query="Laptop được cấp thế nào?", similarity_threshold=0.0)))
    assert not resp.is_refusal and "HR.B2.1" in resp.answer and not repo.tickets


def test_out_of_policy_message_is_declined_instead_of_ticketed():
    llm = RoutingLLM(
        {"intent": "document_question", "standalone_query": "Lương của giám đốc?"}, answers=[REFUSAL_MESSAGE],
        policy={"in_policy": True, "category": "lương, thưởng"},
    )
    uc, repo = _uc(llm)
    resp = asyncio.run(uc.execute(RagChatRequestDTO(query="Lương của giám đốc?", similarity_threshold=0.0)))
    assert resp.intent == "OUT_OF_SCOPE" and "lương, thưởng" in resp.answer and not repo.tickets


def test_grounding_context_without_identifiers_checks_language_only():
    g = GroundingContext(language_guard=True)
    assert g.sentence_problem("Mục ABC.12.X được nhắc tới.") is None
