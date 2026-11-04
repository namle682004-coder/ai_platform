"""
Tests for the evidence-gated, analysis-driven RAG answer pipeline:
lexical evidence, adaptive context selection, answer post-processing, LLM query analysis and the
end-to-end routing in RagChatUseCase (support intents, Self-RAG refusal, unknown identifiers,
conversational rewriting, source footer).
"""

import asyncio
import json
from typing import Any, AsyncGenerator, Dict, List, Tuple

from solutions.rag.application.components.answer_postprocessor import (
    AnswerStreamFilter,
    SanitizeContext,
    build_suggestions,
    sanitize_answer,
)
from solutions.rag.application.components.context_selector import (
    build_document_card,
    candidate_key,
    select_adaptive_context,
)
from solutions.rag.application.components.lexical_evidence import (
    extract_identifiers,
    nearest_existing_codes,
    restore_diacritics_from_corpus,
    score_evidence,
)
from solutions.rag.application.components.prompt_builder import REFUSAL_MESSAGE
from solutions.rag.application.components.query_analyzer import ANALYZER_MARKER, Intent, QueryAnalyzer
from solutions.rag.application.dtos import RagChatRequestDTO
from solutions.rag.application.use_cases.chat_use_case import RagChatUseCase

TITLE = "Quy chế Làm việc Nội bộ"


def _chunk(idx: int, heading: str, text: str, doc_id: str = "doc_hr", title: str = TITLE) -> Dict[str, Any]:
    return {
        "id": f"{doc_id}-{idx}",
        "score": 0.5,
        "payload": {
            "doc_id": doc_id,
            "title": title,
            "chunk_index": idx,
            "page_number": 1 + idx // 3,
            "heading": heading,
            "heading_path": heading,
            "text": f"[Ngữ cảnh: {heading}]\n\n{text}",
        },
    }


CORPUS = [
    _chunk(0, "", f"{TITLE.upper()}\n\n(Ban hành kèm theo QĐ Số: 15/QĐ-CTY ngày 02 tháng 01 năm 2026)"),
    _chunk(1, "CHƯƠNG I", "| Mục | Nội dung | Mã |\n| --- | --- | --- |\n| Giờ làm | Thời gian làm việc | HR.A1.1. Làm việc từ 8h đến 17h. |"),
    _chunk(2, "CHƯƠNG I", "| Mục | Nội dung | Mã |\n| --- | --- | --- |\n| Nghỉ phép | Ngày phép năm | HR.A2.1. Mỗi năm có 12 ngày phép. HR.A2.MR1. Phép thâm niên. |"),
    _chunk(3, "CHƯƠNG II", "| Mục | Nội dung | Mã |\n| --- | --- | --- |\n| Làm việc từ xa | Điều kiện WFH | HR.B1.1. Tối đa 2 ngày mỗi tuần. |"),
    _chunk(4, "CHƯƠNG II", "| Mục | Nội dung | Mã |\n| --- | --- | --- |\n| Thiết bị | Cấp laptop | HR.B2.1. Nhân viên được cấp laptop. |"),
]


# ---------------------------------------------------------------- lexical evidence
def test_verbatim_keyword_gives_high_coverage_even_when_rare():
    report = score_evidence("Phép thâm niên được quy định ở đâu?", CORPUS)
    best = max(range(len(CORPUS)), key=report.coverage_of)
    assert best == 2
    assert report.best_coverage >= 0.5


def test_missing_distinctive_terms_give_low_coverage():
    report = score_evidence("Mức thưởng Tết năm nay cho kỹ sư là bao nhiêu?", CORPUS)
    assert report.best_coverage < 0.15


def test_identifiers_are_generic_and_partial_ids_match_suffix():
    assert extract_identifiers("Xem HR.A2.MR1, QĐ 15/QĐ-CTY, ISO-9001; không phải 2.1.3") == ["HR.A2.MR1", "15/QĐ-CTY", "ISO-9001"]
    report = score_evidence("Mã A2.1 nói gì?", CORPUS)
    assert report.found_identifiers == ["A2.1"]
    missing = score_evidence("Mã HR.A2.MR9 là gì?", CORPUS)
    assert missing.missing_identifiers == ["HR.A2.MR9"]
    scope, codes = nearest_existing_codes("HR.A2.MR9", [c["payload"]["text"] for c in CORPUS])
    assert scope == "HR.A2" and codes == ["HR.A2.1", "HR.A2.MR1"]


def test_numeric_premise_absent_from_passages_is_reported():
    from solutions.rag.application.components.lexical_evidence import absent_numeric_details

    passages = [_chunk(1, "Chương I", "Nhân viên được nghỉ phép 12 ngày mỗi năm theo quy chế ban hành năm 2025.")]
    assert absent_numeric_details("Theo quy chế năm 2019 thì được nghỉ mấy ngày?", passages) == ["năm 2019 thì"]
    assert absent_numeric_details("Nghỉ phép 12 ngày theo quy chế năm 2025 đúng không?", passages) == []
    assert absent_numeric_details("Mã HR.A2.MR1 là gì?", passages) == []
    assert absent_numeric_details("Quy chế 2025 nói về gì?", passages) == []  # number present, other neighbours


def test_unaccented_query_is_reaccented_from_passages():
    restored = restore_diacritics_from_corpus("ngay phep nam", [c["payload"]["text"] for c in CORPUS])
    assert restored == "ngày phép năm"


# ---------------------------------------------------------------- adaptive context
def test_adaptive_context_keeps_whole_section_for_overview_and_orders_by_document():
    report = score_evidence("Chương II gồm những gì?", CORPUS)
    scores = {candidate_key(c): report.coverage_of(i) for i, c in enumerate(CORPUS)}
    selection = select_adaptive_context(CORPUS, scores, relative_cutoff=0.6, min_k=1)
    assert [c["payload"]["chunk_index"] for c in selection.chunks] == [3, 4]


def test_adaptive_context_keeps_dominant_passage_for_specific_question():
    report = score_evidence("Phép thâm niên là gì?", CORPUS)
    scores = {candidate_key(c): report.coverage_of(i) for i, c in enumerate(CORPUS)}
    selection = select_adaptive_context(CORPUS, scores, relative_cutoff=0.6, min_k=1)
    assert [c["payload"]["chunk_index"] for c in selection.chunks] == [2]


def test_document_card_is_verbatim_header_and_outline():
    card = build_document_card(CORPUS)
    text = card.to_context_text()
    assert "15/QĐ-CTY" in text and "02 tháng 01 năm 2026" in text
    assert card.outline == ["CHƯƠNG I", "CHƯƠNG II"]


# ---------------------------------------------------------------- post-processing
def _ctx(**kw) -> SanitizeContext:
    return SanitizeContext(titles=[TITLE], valid_indices={1, 2, 3}, **kw)


def test_model_source_list_is_dropped_structurally_and_markers_renumbered():
    raw = (
        "Mỗi năm có 12 ngày phép [2].\n\n"
        "**Căn cứ:**\n"
        f"- [2] {TITLE.upper().replace('Á', 'á')}, Trang: 1, Mục: CHƯƠNG I\n"
    )
    text, marker_map, refused = sanitize_answer(raw, _ctx())
    assert not refused
    assert text == "Mỗi năm có 12 ngày phép [1]."
    assert marker_map == {2: 1}


def test_heading_followed_by_content_is_kept():
    text, _, _ = sanitize_answer("Kết quả:\n- Làm việc từ 8h [1].", _ctx())
    assert text == "Kết quả:\n- Làm việc từ 8h [1]."


def test_artefacts_are_removed():
    raw = (
        "Tối đa 2 ngày mỗi tuần [1] [Ngữ cảnh: CHƯƠNG II]. 已修正\n"
        "> [!IMPORTANT] Cần đăng ký trước.\n"
        "![Ảnh minh họa](url_anh_1)\n"
    )
    text, _, _ = sanitize_answer(raw, _ctx())
    assert "Ngữ cảnh" not in text and "已修正" not in text and "url_anh_1" not in text
    assert "**Lưu ý:** Cần đăng ký trước." in text


def test_refusal_sentence_is_detected_before_streaming():
    f = AnswerStreamFilter(_ctx())
    emitted = []
    for token in [REFUSAL_MESSAGE[:20], REFUSAL_MESSAGE[20:], " Thêm"]:
        emitted += f.feed(token)
    emitted += f.finish()
    assert f.refused and emitted == []


def test_reformatted_refusal_is_detected_and_nothing_leaks():
    first_word, rest = REFUSAL_MESSAGE.split(" ", 1)
    variants = [
        f"{first_word}\n{rest}",  # line break after the first word used to stream "Hiện" alone
        f"**{REFUSAL_MESSAGE}**",
        f"> {REFUSAL_MESSAGE}",
        f"{first_word} tại, {rest[0].lower()}{rest[1:]}",
    ]
    for raw in variants:
        f = AnswerStreamFilter(_ctx())
        emitted = []
        for i in range(0, len(raw), 3):
            emitted += f.feed(raw[i:i + 3])
        emitted += f.finish()
        assert f.refused and emitted == [], raw


def test_refusal_followed_by_evidenced_answer_keeps_the_answer():
    from solutions.rag.application.components.answer_postprocessor import PARTIAL_ANSWER_OPENING

    raw = f"{REFUSAL_MESSAGE} Tuy nhiên, phép thâm niên được quy định ở mục HR.A2.MR1 [1]."
    f = AnswerStreamFilter(_ctx())
    emitted = []
    for i in range(0, len(raw), 4):
        emitted += f.feed(raw[i:i + 4])
    emitted += f.finish()
    text = "".join(emitted)
    assert not f.refused and text.startswith(PARTIAL_ANSWER_OPENING) and "HR.A2.MR1 [1]" in text

    bare = sanitize_answer(f"{REFUSAL_MESSAGE} Vui lòng hỏi lại sau.", _ctx())
    assert bare[2] is True


def test_answer_sharing_the_refusal_opening_is_not_a_refusal():
    opening = " ".join(REFUSAL_MESSAGE.split()[:6])
    raw = f"{opening} về mục này, nhưng mục liên quan quy định thời hạn 30 ngày [1]."
    text, _, refused = sanitize_answer(raw, _ctx())
    assert not refused and "30 ngày" in text


def test_streaming_output_equals_batch_output():
    raw = (
        "Nhân viên được làm việc từ xa tối đa hai ngày mỗi tuần theo quy chế hiện hành của công ty [3], "
        "và phải đăng ký với quản lý trực tiếp trước khi áp dụng [1].\n- Thiết bị: laptop [3].\n\nNguồn:\n"
        f"[1] {TITLE} – Trang 2\n"
    )
    batch, _, _ = sanitize_answer(raw, _ctx())
    f = AnswerStreamFilter(_ctx())
    pieces: List[str] = []
    for i in range(0, len(raw), 7):
        pieces += f.feed(raw[i:i + 7])
    pieces += f.finish()
    assert "".join(pieces).strip() == batch
    assert "[1]" in batch and "[2]" in batch and "Nguồn" not in batch


def test_suggestions_come_from_same_group_rows():
    tip = build_suggestions("Mỗi năm có 12 ngày phép (HR.A2.1).", CORPUS)
    # The answered row (HR.A2.1 / HR.A2.MR1) is not suggested again; real rows from other passages are.
    assert "HR.A2" not in tip
    assert "«Thời gian làm việc» (CHƯƠNG I, Giờ làm: HR.A1.1)" in tip


# ---------------------------------------------------------------- query analyzer
def test_analyzer_parses_json_and_falls_back_on_garbage():
    qa = QueryAnalyzer(out_of_scope_policy="lương")
    history = [{"role": "user", "content": "Chương I gồm những gì?"}, {"role": "assistant", "content": "..."}]
    parsed = qa.parse('```json\n{"intent": "document_question", "standalone_query": "Chương II gồm những gì?", "new_topic": false}\n```', "Còn chương II?", history, 1.0)
    assert parsed.intent == Intent.DOCUMENT_QUESTION and parsed.standalone_query == "Chương II gồm những gì?"
    phone = qa.parse('{"intent": "support_request"}', "Có, số của tôi là 0900 123 456.", history, 1.0)
    assert phone.intent == Intent.CONTACT_INFO and phone.phone == "0900123456"
    lossy = qa.parse('{"intent": "document_question", "standalone_query": "Tài liệu có tên là gì?"}', "HR.A2.MR1", [], 1.0)
    assert lossy.standalone_query == "HR.A2.MR1"
    fallback = qa.parse("not json", "Còn chương II?", history, 1.0)
    assert fallback.source == "fallback" and fallback.standalone_query.startswith("Chương I gồm những gì")


# ---------------------------------------------------------------- end-to-end use case
class ScriptedLLM:
    """Returns a fixed analysis JSON for analyzer calls and a fixed answer for generation calls."""

    def __init__(self, analysis: Dict[str, Any], answer: str):
        self.analysis = analysis
        self.answer = answer
        self.calls: List[List[Dict[str, str]]] = []

    async def generate(self, messages, model, temperature=0.2, max_tokens=1024, authorization=None) -> Tuple[str, int, int]:
        self.calls.append(messages)
        if ANALYZER_MARKER in messages[0]["content"]:
            return json.dumps(self.analysis, ensure_ascii=False), 10, 10
        return self.answer, 10, 10

    async def stream_generate(self, messages, model, temperature=0.2, max_tokens=1024, authorization=None) -> AsyncGenerator[str, None]:
        self.calls.append(messages)
        for i in range(0, len(self.answer), 5):
            yield self.answer[i:i + 5]


class CorpusStore:
    def __init__(self):
        self.queries: List[str] = []

    async def search(self, **kwargs) -> List[Dict[str, Any]]:
        self.queries.append(kwargs.get("query_text", ""))
        return [dict(c) for c in CORPUS]

    async def fetch_document_chunks(self, doc_id, tenant_id, user_role="user", limit=300):
        return [dict(c) for c in CORPUS if c["payload"]["doc_id"] == doc_id]


class Embedder:
    async def get_embedding(self, text: str) -> List[float]:
        return [0.1] * 8


class Repo:
    def __init__(self):
        self.tickets: List[Dict[str, Any]] = []
        self.turns: List[Tuple[Dict[str, Any], Dict[str, Any]]] = []

    async def get_session(self, *args, **kwargs):
        return None

    async def append_turn(self, session_id, user_id, tenant_id, user_msg, assistant_msg, title=None):
        self.turns.append((user_msg, assistant_msg))
        return True

    async def record_escalation_ticket(self, ticket):
        self.tickets.append(ticket)
        return ticket["ticket_id"]


class ScoreReranker:
    """Cross-encoder stand-in: scores passages by keyword coverage."""

    async def arerank(self, query, candidates, top_n=5, min_threshold=0.0):
        report = score_evidence(query, candidates)
        scored = [dict(c, score=report.coverage_of(i)) for i, c in enumerate(candidates)]
        return sorted(scored, key=lambda c: c["score"], reverse=True)[:top_n]


def _use_case(llm) -> Tuple[RagChatUseCase, CorpusStore, Repo]:
    store, repo = CorpusStore(), Repo()
    return RagChatUseCase(store, Embedder(), llm, repo, reranker_service=ScoreReranker()), store, repo


class SmallWindowLLM(ScriptedLLM):
    """A runtime with a small context window that records the completion budget it was asked for."""

    def __init__(self, analysis, answer, window):
        super().__init__(analysis, answer)
        self.window = window
        self.max_tokens: List[int] = []

    async def context_window(self, model):
        return self.window

    async def generate(self, messages, model, temperature=0.2, max_tokens=1024, authorization=None):
        if ANALYZER_MARKER not in messages[0]["content"]:
            self.max_tokens.append(max_tokens)
        return await super().generate(messages, model, temperature, max_tokens, authorization)


def test_prompt_is_fitted_to_the_runtime_context_window():
    from solutions.rag.config import rag_settings

    analysis = {"intent": "document_question", "standalone_query": "Liệt kê toàn bộ quy định về nghỉ phép", "wants_list": True}
    request = dict(query="Liệt kê toàn bộ quy định về nghỉ phép", similarity_threshold=0.0, max_tokens=1024)
    wide = SmallWindowLLM(analysis, "Theo quy chế [1].", window=None)
    asyncio.run(_use_case(wide)[0].execute(RagChatRequestDTO(**request)))
    full_prompt = wide.calls[-1][0]["content"]
    assert wide.max_tokens[-1] == 1024

    # One token short of fitting the full context plus the minimum completion: a passage must go.
    cpt = rag_settings.llm_chars_per_token
    full_tokens = int(sum(len(m["content"]) for m in wide.calls[-1]) / cpt)
    window = full_tokens + rag_settings.llm_min_completion_tokens + rag_settings.llm_prompt_safety_tokens - 1
    narrow = SmallWindowLLM(analysis, "Theo quy chế [1].", window=window)
    asyncio.run(_use_case(narrow)[0].execute(RagChatRequestDTO(**request)))
    messages = narrow.calls[-1]
    prompt_tokens = sum(len(m["content"]) for m in messages) / cpt
    assert len(messages[0]["content"]) < len(full_prompt)
    assert prompt_tokens + narrow.max_tokens[-1] <= window
    assert narrow.max_tokens[-1] >= rag_settings.llm_min_completion_tokens


def test_unclear_verdict_is_verified_against_retrieval():
    supported = ScriptedLLM({"intent": "unclear"}, "Có phép thâm niên theo HR.A2.MR1 [1].")
    resp = asyncio.run(_use_case(supported)[0].execute(RagChatRequestDTO(query="Phép thâm niên được quy định thế nào?", similarity_threshold=0.65)))
    assert resp.intent == "QA_STUFF" and resp.answer.startswith("Có phép thâm niên")

    first_turn_feedback = ScriptedLLM({"intent": "feedback"}, "Có phép thâm niên theo HR.A2.MR1 [1].")
    uc, _, repo = _use_case(first_turn_feedback)
    resp = asyncio.run(uc.execute(RagChatRequestDTO(query="Phép thâm niên được quy định thế nào?", similarity_threshold=0.65)))
    assert resp.intent == "QA_STUFF" and not repo.tickets

    real_feedback = ScriptedLLM({"intent": "feedback"}, "unused")
    uc, _, repo = _use_case(real_feedback)
    resp = asyncio.run(uc.execute(RagChatRequestDTO(query="Câu vừa rồi chưa đúng ý, tôi muốn báo lỗi.", similarity_threshold=0.65)))
    assert resp.intent == "FEEDBACK" and repo.tickets and repo.tickets[0]["reason"] == "user_feedback"

    unsupported = ScriptedLLM({"intent": "unclear"}, "unused")
    uc, _, repo = _use_case(unsupported)
    resp = asyncio.run(uc.execute(RagChatRequestDTO(query="Cái đó thì sao?", similarity_threshold=0.65)))
    assert resp.intent == "CLARIFICATION" and not repo.tickets


def test_follow_up_is_rewritten_before_retrieval_and_answer_gets_footer():
    llm = ScriptedLLM(
        {"intent": "document_question", "standalone_query": "Phép thâm niên được quy định thế nào?", "challenge": False},
        "Có phép thâm niên theo HR.A2.MR1 [1].\n\nNguồn:\n[1] QUY CHẾ LÀM VIỆC NỘI BỘ – Trang 1",
    )
    uc, store, repo = _use_case(llm)
    history = [{"role": "user", "content": "Ngày phép năm là bao nhiêu?"}, {"role": "assistant", "content": "12 ngày."}]
    resp = asyncio.run(uc.execute(RagChatRequestDTO(query="Còn thâm niên thì sao?", history=history, similarity_threshold=0.65)))
    assert store.queries[0].startswith("Phép thâm niên")
    assert resp.intent == "QA_STUFF" and not resp.is_refusal
    assert resp.answer.startswith("Có phép thâm niên theo HR.A2.MR1 [1].")
    assert f"[1] {TITLE}" in resp.answer and "QUY CHẾ LÀM VIỆC NỘI BỘ –" not in resp.answer
    assert repo.turns[-1][0]["standalone"] == "Phép thâm niên được quy định thế nào?"


def test_model_refusal_becomes_escalation_with_ticket():
    llm = ScriptedLLM({"intent": "document_question", "standalone_query": "Laptop được cấp cấu hình gì?"}, REFUSAL_MESSAGE)
    uc, _, repo = _use_case(llm)
    resp = asyncio.run(uc.execute(RagChatRequestDTO(query="Laptop được cấp cấu hình gì?", similarity_threshold=0.65)))
    assert resp.intent == "REFUSAL" and resp.is_refusal and resp.status == "escalation_required"
    ticket = repo.tickets[-1]["ticket_id"]
    assert resp.answer.startswith(REFUSAL_MESSAGE) and ticket in resp.answer


def test_streaming_model_refusal_is_replaced_by_escalation():
    llm = ScriptedLLM({"intent": "document_question", "standalone_query": "Laptop được cấp cấu hình gì?"}, REFUSAL_MESSAGE)
    uc, _, repo = _use_case(llm)

    async def run():
        return [e async for e in uc.stream_execute(RagChatRequestDTO(query="Laptop được cấp cấu hình gì?", stream=True, similarity_threshold=0.65))]

    events = asyncio.run(run())
    tokens = "".join(json.loads(e[6:])["token"] for e in events if '"token"' in e)
    done = json.loads(events[-1][6:])
    assert tokens.startswith(REFUSAL_MESSAGE) and repo.tickets[-1]["ticket_id"] in tokens
    assert done["intent"] == "REFUSAL" and done["is_refusal"] is True


def test_support_request_returns_contact_channels_and_ticket():
    llm = ScriptedLLM({"intent": "support_request"}, "unused")
    uc, store, repo = _use_case(llm)
    resp = asyncio.run(uc.execute(RagChatRequestDTO(query="Cho tôi gặp nhân viên hỗ trợ")))
    assert resp.intent == "ESCALATION" and repo.tickets[-1]["reason"] == "handoff_request"
    assert "Hotline" in resp.answer and repo.tickets[-1]["ticket_id"] in resp.answer
    assert store.queries == []  # no retrieval for support turns


def test_contact_number_is_attached_to_ticket_of_unanswered_question():
    llm = ScriptedLLM({"intent": "contact_info", "phone": "0912 345 678"}, "unused")
    uc, _, repo = _use_case(llm)
    history = [
        {"role": "user", "content": "Laptop được cấp cấu hình gì?"},
        {"role": "assistant", "content": REFUSAL_MESSAGE + " ticket_abcdef1234"},
    ]
    resp = asyncio.run(uc.execute(RagChatRequestDTO(query="Số của tôi 0912 345 678", history=history)))
    assert resp.intent == "CONTACT_CAPTURED"
    assert repo.tickets[-1]["contact_phone"] == "0912345678"
    assert repo.tickets[-1]["query"] == "Laptop được cấp cấu hình gì?"
    assert "091****678" in resp.answer


def test_unknown_identifier_is_answered_without_generation():
    llm = ScriptedLLM({"intent": "document_question", "standalone_query": "Mã HR.B1.MR5 là gì?"}, "should not be used")
    uc, _, _ = _use_case(llm)
    resp = asyncio.run(uc.execute(RagChatRequestDTO(query="Mã HR.B1.MR5 là gì?", similarity_threshold=0.65)))
    assert resp.intent == "IDENTIFIER_NOT_FOUND"
    assert "HR.B1.MR5" in resp.answer and "HR.B1.1" in resp.answer
    assert all(ANALYZER_MARKER in m[0]["content"] for m in llm.calls)


def test_out_of_scope_is_declined_with_reason():
    llm = ScriptedLLM({"intent": "out_of_scope", "out_of_scope_category": "lương, thưởng"}, "unused")
    uc, _, _ = _use_case(llm)
    resp = asyncio.run(uc.execute(RagChatRequestDTO(query="Lương giám đốc bao nhiêu?")))
    assert resp.intent == "OUT_OF_SCOPE" and "lương, thưởng" in resp.answer


# ---------------------------------------------------------------- LLM runtime adapter
def _adapter(handler):
    import httpx

    from solutions.rag.infrastructure.adapters.llm_adapter import HttpLlmAdapter

    adapter = HttpLlmAdapter(base_url="http://llm.test/v1")
    adapter._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return adapter


def test_runtime_error_event_mid_stream_is_raised_not_returned_as_answer():
    import httpx
    import pytest

    from solutions.rag.domain.exceptions import LLMGenerationError

    body = (
        'data: {"choices": [{"delta": {"content": "Lớ"}}]}\n\n'
        'data: {"error": {"code": 500, "message": "Context size has been exceeded."}}\n\n'
    )
    adapter = _adapter(lambda request: httpx.Response(200, text=body, headers={"content-type": "text/event-stream"}))

    async def consume():
        return [t async for t in adapter.stream_generate([{"role": "user", "content": "x"}], "m")]

    with pytest.raises(LLMGenerationError):
        asyncio.run(consume())


def test_context_window_is_read_from_the_runtime():
    import httpx

    def handler(request):
        if request.url.path == "/props":
            return httpx.Response(200, json={"default_generation_settings": {"n_ctx": 4096}})
        return httpx.Response(404)

    assert asyncio.run(_adapter(handler).context_window("m")) == 4096


def test_reranker_pairs_fit_the_runtime_batch():
    import httpx

    from solutions.rag.config import rag_settings
    from solutions.rag.infrastructure.adapters.reranker_adapter import HttpCrossEncoderReranker

    sent = {}

    def handler(request):
        sent.update(json.loads(request.content))
        return httpx.Response(200, json={"results": [{"index": i, "relevance_score": 0.5} for i in range(2)]})

    reranker = HttpCrossEncoderReranker(base_url="http://rerank.test/v1")
    reranker._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    long_text = "nội dung " * 2000
    candidates = [{"text": long_text, "title": TITLE}, {"text": "ngắn", "title": TITLE}]
    asyncio.run(reranker.arerank("câu hỏi " * 300, candidates, top_n=2, min_threshold=0.0))
    budget = rag_settings.reranker_max_input_tokens * rag_settings.reranker_chars_per_token
    assert all(len(sent["query"]) + len(doc) <= budget for doc in sent["documents"])
