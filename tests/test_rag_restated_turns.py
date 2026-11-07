"""
A message with nothing to look up ("HI", a complaint about the last answer) must not be answered with the
previous answer again. The analyzer of a small model rewrites such messages into the session's last
question; the rewrite is re-checked with a narrow request / greeting / feedback question.
"""

import asyncio
import json

from solutions.rag.application.components.query_analyzer import (
    ANALYZER_MARKER,
    Intent,
    QueryAnalyzer,
    restates_history,
)
from solutions.rag.application.dtos import RagChatRequestDTO

from test_rag_answer_pipeline import ScriptedLLM, _use_case

FIRST_Q = "Tour du lịch ngắm voi ở Yok Đôn là gì? kèm theo ảnh đi kèm"
FIRST_A = (
    "Tour du lịch ngắm voi ở Vườn quốc gia Yok Đôn, Đắk Lắk là một trải nghiệm đặc biệt, du khách đi bộ "
    "băng rừng để tìm gặp những chú voi [1]."
)
# What the analyzer actually returned for "HI" and "MÀY TRẢ LỜI GÌ VẬY" (trace of the reported session).
RESTATED = "Tour du lịch ngắm voi ở Vườn quốc gia Yok Đôn, Đắk Lắk là gì?"
HISTORY = [
    {"role": "user", "content": FIRST_Q, "standalone": "Tour du lịch ngắm voi ở Yok Đôn là gì?"},
    {"role": "assistant", "content": FIRST_A},
]


class KindLLM(ScriptedLLM):
    """Analyzer returns `analysis`; the narrow message-kind check returns `kind`."""

    def __init__(self, analysis, answer, kind):
        super().__init__(analysis, answer)
        self.kind = kind
        self.kind_calls = 0

    async def generate(self, messages, model, temperature=0.2, max_tokens=1024, authorization=None):
        system = messages[0]["content"]
        if ANALYZER_MARKER in system and '"kind"' in system:
            self.kind_calls += 1
            return json.dumps({"kind": self.kind}), 5, 5
        return await super().generate(messages, model, temperature, max_tokens, authorization)


def _analysis(llm, query, history=HISTORY):
    return asyncio.run(QueryAnalyzer().analyze(query, history, llm, "m"))


def test_rewrite_made_of_history_words_is_flagged():
    texts = [FIRST_Q, "Tour du lịch ngắm voi ở Yok Đôn là gì?", FIRST_A]
    assert restates_history("HI", RESTATED, texts)
    assert restates_history("MÀY TRẢ LỜI GÌ VẬY", RESTATED, texts)
    # A follow-up that brings its own words is a new question, not a restatement.
    assert not restates_history("Còn ở Cát Tiên thì sao?", "Tour du lịch ngắm voi ở Cát Tiên là gì?", texts)
    assert not restates_history("Giá vé tour bao nhiêu?", "Giá vé tour du lịch ngắm voi ở Yok Đôn là bao nhiêu?", texts)
    assert not restates_history("HI", RESTATED, [])


def test_greeting_rewritten_as_previous_question_becomes_greeting():
    llm = KindLLM({"intent": "document_question", "standalone_query": RESTATED}, "unused", kind="greeting")
    a = _analysis(llm, "HI")
    assert a.intent == Intent.GREETING and a.message_kind == "greeting" and a.standalone_query == "HI"


def test_complaint_rewritten_as_previous_question_becomes_feedback():
    llm = KindLLM({"intent": "document_question", "standalone_query": RESTATED}, "unused", kind="feedback")
    a = _analysis(llm, "MÀY TRẢ LỜI GÌ VẬY")
    assert a.intent == Intent.FEEDBACK and a.challenge


def test_real_follow_up_request_keeps_the_rewrite():
    llm = KindLLM({"intent": "document_question", "standalone_query": RESTATED}, "unused", kind="request")
    a = _analysis(llm, "Giải thích thêm đi")
    assert a.intent == Intent.DOCUMENT_QUESTION and a.standalone_query == RESTATED and a.message_kind == "request"


def test_check_is_skipped_when_the_message_carries_its_own_question():
    llm = KindLLM(
        {"intent": "document_question", "standalone_query": "Giá vé tour du lịch ngắm voi ở Yok Đôn là bao nhiêu?"},
        "unused", kind="greeting",
    )
    a = _analysis(llm, "Giá vé tour bao nhiêu?")
    assert a.intent == Intent.DOCUMENT_QUESTION and llm.kind_calls == 0


def test_unavailable_check_keeps_the_analyzer_decision():
    llm = KindLLM({"intent": "document_question", "standalone_query": RESTATED}, "unused", kind="???")
    a = _analysis(llm, "HI")
    assert a.intent == Intent.DOCUMENT_QUESTION and a.message_kind == ""


def test_greeting_after_an_answer_is_not_answered_from_documents():
    llm = KindLLM({"intent": "document_question", "standalone_query": RESTATED}, "PREVIOUS ANSWER [1].", kind="greeting")
    uc, store, _ = _use_case(llm)
    resp = asyncio.run(uc.execute(RagChatRequestDTO(query="HI", history=HISTORY, similarity_threshold=0.65)))
    assert resp.intent == "CHITCHAT" and "PREVIOUS ANSWER" not in resp.answer
    assert not store.queries  # nothing retrieved


def test_complaint_after_an_answer_is_recorded_as_feedback_not_repeated():
    llm = KindLLM({"intent": "document_question", "standalone_query": RESTATED}, "PREVIOUS ANSWER [1].", kind="feedback")
    uc, _, repo = _use_case(llm)
    resp = asyncio.run(uc.execute(RagChatRequestDTO(query="MÀY TRẢ LỜI GÌ VẬY", history=HISTORY, similarity_threshold=0.65)))
    assert resp.intent == "FEEDBACK" and "PREVIOUS ANSWER" not in resp.answer
    assert repo.tickets and repo.tickets[0]["reason"] == "user_feedback"


# ---------------------------------------------------------------- analyzer unavailable (fallback)
class DownLLM(ScriptedLLM):
    """The analyzer times out / errors: the fallback analysis is used."""

    async def generate(self, messages, model, temperature=0.2, max_tokens=1024, authorization=None):
        if ANALYZER_MARKER in messages[0]["content"]:
            raise RuntimeError("runtime down")
        return await super().generate(messages, model, temperature, max_tokens, authorization)


def test_fallback_does_not_carry_the_previous_question_into_a_greeting():
    from test_rag_answer_pipeline import CorpusStore

    llm = DownLLM({}, "PREVIOUS ANSWER [1].")
    uc, _, _ = _use_case(llm)
    uc.vector_store = CorpusStore()
    history = [{"role": "user", "content": "Ngày phép năm là bao nhiêu?"}, {"role": "assistant", "content": "12 ngày [1]."}]
    resp = asyncio.run(uc.execute(RagChatRequestDTO(query="HI", history=history, similarity_threshold=0.65)))
    assert "PREVIOUS ANSWER" not in resp.answer and resp.intent == "CLARIFICATION"


def test_fallback_still_joins_a_real_follow_up():
    llm = DownLLM({}, "Có phép thâm niên theo HR.A2.MR1 [1].")
    uc, store, _ = _use_case(llm)
    history = [{"role": "user", "content": "Ngày phép năm là bao nhiêu?"}, {"role": "assistant", "content": "12 ngày [1]."}]
    asyncio.run(uc.execute(RagChatRequestDTO(query="Còn thâm niên?", history=history, similarity_threshold=0.65)))
    assert any("Ngày phép năm" in q and "thâm niên" in q for q in store.queries)


def test_rewrite_keeps_the_spelling_of_words_typed_with_diacritics():
    from solutions.rag.application.components.query_analyzer import keep_typed_spelling

    # The trace of the reported session: "ngắm voi" (elephant watching) rewritten as "ngắm với".
    assert keep_typed_spelling("Tour du lịch ngắm với ở Yok Đôn là gì?", FIRST_Q) == "Tour du lịch ngắm voi ở Yok Đôn là gì?"
    # Words the user did not type are untouched; an unaccented message still gets its accents restored.
    assert keep_typed_spelling("Lớp 10 học những chủ đề nào?", "lop 10 hoc nhung gi") == "Lớp 10 học những chủ đề nào?"
