"""
Per-turn pipeline traces: what the use case records per stage, how it is stored (PII-masked,
tail-sampled), the quality metrics derived from it, and the stage diagnosis that attributes a
failed answer to the stage that lost the evidence.
"""

import asyncio
import json
from typing import Any, Dict, List

from solutions.rag.application.components.prompt_builder import REFUSAL_MESSAGE
from solutions.rag.application.components.run_trace import TurnTrace, chunk_ref
from solutions.rag.application.components.trace_diagnosis import diagnose
from solutions.rag.application.dtos import RagChatRequestDTO
from solutions.rag.application.use_cases.chat_use_case import RagChatUseCase
from solutions.rag.domain.ports import NullObservabilityAdapter
from solutions.rag.infrastructure.repositories.mongo_trace_store import MongoTraceStore
from tests.test_rag_answer_pipeline import CorpusStore, Embedder, Repo, ScoreReranker, ScriptedLLM

ANSWER = "Mỗi năm có 12 ngày phép theo HR.A2.1 [1]."


class RecordingObs(NullObservabilityAdapter):
    def __init__(self):
        self.outcomes: List[tuple] = []
        self.verifications: List[tuple] = []

    def record_answer_outcome(self, route, intent, refused, tenant_id="t"):
        self.outcomes.append((route, intent, refused))

    def record_verification(self, problems, corrected, tenant_id="t"):
        self.verifications.append((list(problems), corrected))


def _use_case(llm):
    store, obs = MongoTraceStore(mongo_uri=""), RecordingObs()
    uc = RagChatUseCase(CorpusStore(), Embedder(), llm, Repo(), reranker_service=ScoreReranker(),
                        observability_service=obs, trace_store=store)
    return uc, store, obs


def _stages(trace: Dict[str, Any]) -> List[str]:
    return [s["stage"] for s in trace["stages"]]


def test_generated_turn_is_traced_stage_by_stage_under_the_request_trace_id():
    llm = ScriptedLLM({"intent": "document_question", "standalone_query": "Mỗi năm có bao nhiêu ngày phép?"}, ANSWER)
    uc, store, obs = _use_case(llm)

    async def run():
        resp = await uc.execute(RagChatRequestDTO(query="Mỗi năm có bao nhiêu ngày phép?", similarity_threshold=0.65),
                                tenant_id="tenant_a", trace_id="rag-req-1")
        await uc.flush_traces()
        return resp, await store.get("rag-req-1", "tenant_a")

    resp, trace = asyncio.run(run())
    assert resp.telemetry["trace_id"] == "rag-req-1"
    stages = _stages(trace)
    for stage in ("query_analysis", "retrieval", "rerank", "gate", "context", "generation", "verification", "route"):
        assert stage in stages, stage
    qa = next(s for s in trace["stages"] if s["stage"] == "query_analysis")
    assert qa["standalone_query"] == "Mỗi năm có bao nhiêu ngày phép?" and qa["intent"] == "document_question"
    ctx = next(s for s in trace["stages"] if s["stage"] == "context")
    assert any("HR.A2.1" in c["ids"] and "12 ngày phép" in c["text"] for c in ctx["chunks"])
    assert next(s for s in trace["stages"] if s["stage"] == "gate")["decision"] == "pass"
    assert next(s for s in trace["stages"] if s["stage"] == "generation")["raw_answer"] == ANSWER
    assert trace["outcome"]["intent"] == "QA_STUFF" and trace["outcome"]["answer"] == resp.answer
    assert trace["outcome"]["route"] == "generate" and trace["config"]["gate_min_rerank_score"] is not None
    assert obs.outcomes == [("generate", "QA_STUFF", False)]
    # A store of another tenant never sees the trace.
    assert asyncio.run(store.get("rag-req-1", "tenant_b")) is None


def test_streamed_turn_trace_matches_what_the_client_received():
    llm = ScriptedLLM({"intent": "document_question", "standalone_query": "Mỗi năm có bao nhiêu ngày phép?"}, ANSWER)
    uc, store, _ = _use_case(llm)

    async def run():
        events = [e async for e in uc.stream_execute(
            RagChatRequestDTO(query="Mỗi năm có bao nhiêu ngày phép?", stream=True, similarity_threshold=0.65),
            tenant_id="tenant_a", trace_id="rag-stream-1",
        )]
        await uc.flush_traces()
        return events, await store.get("rag-stream-1", "tenant_a")

    events, trace = asyncio.run(run())
    tokens = "".join(json.loads(e[6:])["token"] for e in events if '"token"' in e)
    done = json.loads(events[-1][6:])
    assert done["trace_id"] == "rag-stream-1"
    assert trace["endpoint"] == "stream" and trace["outcome"]["answer"] == tokens
    assert trace["outcome"]["ttft_ms"] is not None and trace["outcome"]["intent"] == done["intent"]
    assert "generation" in _stages(trace) and "verification" in _stages(trace)


def test_model_refusal_route_is_traced_and_counted():
    llm = ScriptedLLM({"intent": "document_question", "standalone_query": "Laptop được cấp cấu hình gì?"}, REFUSAL_MESSAGE)
    uc, store, obs = _use_case(llm)

    async def run():
        resp = await uc.execute(RagChatRequestDTO(query="Laptop được cấp cấu hình gì?", similarity_threshold=0.65),
                                tenant_id="t", trace_id="rag-ref")
        await uc.flush_traces()
        return resp, await store.get("rag-ref", "t")

    resp, trace = asyncio.run(run())
    assert resp.is_refusal and trace["outcome"]["is_refusal"]
    assert trace["outcome"]["route"] == "generation_refusal"
    assert "refusal_recovery" in _stages(trace)
    assert obs.outcomes[-1] == ("generation_refusal", "REFUSAL", True)


def test_support_turn_skips_retrieval_and_is_routed_as_support(monkeypatch):
    from solutions.rag.config import rag_settings

    # Routing only: the speculative first-message search (run during analysis, then cancelled for
    # non-document turns) is covered by test_rag_speculative_retrieval.py.
    monkeypatch.setattr(rag_settings, "speculative_retrieval_enabled", False)
    uc, store, obs = _use_case(ScriptedLLM({"intent": "support_request"}, "unused"))

    async def run():
        await uc.execute(RagChatRequestDTO(query="Cho tôi gặp nhân viên hỗ trợ"), tenant_id="t", trace_id="rag-sup")
        await uc.flush_traces()
        return await store.get("rag-sup", "t")

    trace = asyncio.run(run())
    assert "retrieval" not in _stages(trace) and trace["outcome"]["route"] == "support"


def test_stored_trace_masks_personal_data_typed_by_the_user():
    t = TurnTrace(trace_id="x", tenant_id="t", session_id="s", user_id="u", query="Số của tôi là 0912345678")
    t.add("generation", raw_answer="Đã ghi nhận số 0912345678, email a.b@example.com")
    t.outcome = {"answer": "Đã ghi nhận số 0912345678"}
    rec = t.to_record(redact=True)
    blob = json.dumps(rec, ensure_ascii=False)
    assert "0912345678" not in blob and "a.b@example.com" not in blob
    assert "[PHONE_REDACTED]" in rec["query"]


def test_tail_sampling_keeps_refusals_and_corrections():
    t = TurnTrace(trace_id="x", tenant_id="t", session_id="s", user_id="u", query="q", sampled=False)
    assert not t.should_keep()
    t.add("correction", hints=["…"], accepted=True)
    assert t.should_keep()
    t2 = TurnTrace(trace_id="y", tenant_id="t", session_id="s", user_id="u", query="q", sampled=False)
    t2.outcome = {"is_refusal": True}
    assert t2.should_keep()


def test_feedback_is_attached_and_rated_traces_are_listed():
    store = MongoTraceStore(mongo_uri="")

    async def run():
        await store.save({"trace_id": "a", "tenant_id": "t", "created_at": 1.0, "stages": [], "outcome": {}})
        await store.save({"trace_id": "b", "tenant_id": "t", "created_at": 2.0, "stages": [], "outcome": {}})
        assert await store.attach_feedback("a", "t", {"polarity": "negative"})
        return await store.list("t", feedback="negative"), await store.list("t")

    negative, recent = asyncio.run(run())
    assert [t["trace_id"] for t in negative] == ["a"]
    assert [t["trace_id"] for t in recent] == ["b", "a"]


# ---------------------------------------------------------------------------
# Stage diagnosis
# ---------------------------------------------------------------------------

def _ref(doc: str, idx: int, ids: List[str], text: str = "") -> Dict[str, Any]:
    return {"doc_id": doc, "chunk_index": idx, "ids": ids, "text": text}


def _trace(retrieved, ranked, context, answer, gate="pass", route="generate", generation=None, dropped=None):
    stages = [
        {"stage": "query_analysis"},
        {"stage": "retrieval", "candidates": retrieved},
        {"stage": "rerank", "ranked": ranked},
        {"stage": "gate", "decision": gate, "top_rerank": 0.1, "best_lexical": 0.1, "min_rerank": 0.3},
    ]
    if context is not None:
        stages.append({"stage": "context", "chunks": context})
    if generation is not None:
        stages.append({"stage": "generation", "raw_answer": generation})
        stages.append({"stage": "verification", "dropped": dropped or []})
    stages.append({"stage": "route", "route": route})
    return {"stages": stages, "outcome": {"answer": answer}, "config": {"context_max_chunks": 2}}


GOLD = _ref("d", 5, ["X.1"], "X.1 nội dung đúng")
NOISE = [_ref("d", i, [f"N.{i}"]) for i in range(4)]


def test_diagnosis_blames_ingestion_when_gold_is_not_indexed():
    d = diagnose(_trace(NOISE, NOISE, NOISE[:2], "sai"), ["X.1"], indexed=[], answer_correct=False)
    assert d.stage == "ingestion"


def test_diagnosis_blames_retrieval_rerank_and_context():
    assert diagnose(_trace(NOISE, NOISE, NOISE[:2], "sai"), ["X.1"], indexed=["X.1"]).stage == "retrieval"
    ranked = NOISE + [GOLD]
    assert diagnose(_trace(ranked, ranked, NOISE[:2], "sai"), ["X.1"]).stage == "rerank"
    ranked = [GOLD] + NOISE
    assert diagnose(_trace(ranked, ranked, NOISE[:2], "sai"), ["X.1"]).stage == "context"


def test_diagnosis_blames_gate_and_routing():
    ranked = [GOLD] + NOISE
    assert diagnose(_trace(ranked, ranked, None, REFUSAL_MESSAGE, gate="no_evidence", route="gate_refusal"),
                    ["X.1"]).stage == "gate"
    support = {"stages": [{"stage": "route", "route": "support"}], "outcome": {"answer": "Liên hệ hotline"}}
    assert diagnose(support, ["X.1"]).stage == "routing"


def test_diagnosis_separates_verification_from_generation():
    ranked = [GOLD] + NOISE
    removed = _trace(ranked, ranked, [GOLD], "Câu trả lời", generation="Theo X.1 là đúng.",
                     dropped=[{"problem": "number:5", "sentence": "Theo X.1 là đúng."}])
    assert diagnose(removed, ["X.1"], answer_correct=False).stage == "verification"
    wrong = _trace(ranked, ranked, [GOLD], "Theo X.1 là sai.", generation="Theo X.1 là sai.")
    assert diagnose(wrong, ["X.1"], answer_correct=False).stage == "generation"
    assert diagnose(wrong, ["X.1"], answer_correct=True).stage is None


def test_diagnosis_of_unanswerable_question_answered_anyway_is_generation():
    t = _trace(NOISE, NOISE, NOISE[:2], "Lớp 10 học 2 tiết mỗi tuần.")
    assert diagnose(t, [], expect_answer=False, answer_correct=False).stage == "generation"
    refused = _trace(NOISE, NOISE, None, REFUSAL_MESSAGE, gate="no_evidence", route="gate_refusal")
    assert diagnose(refused, [], expect_answer=False, answer_correct=True).stage is None


def test_chunk_ref_keeps_identifiers_and_bounded_text():
    ref = chunk_ref({"id": 1, "score": 0.42, "payload": {"doc_id": "d", "chunk_index": 3, "title": "T",
                                                         "text": "Mã 11.C3.MR4 và 2422/QĐ-BGDĐT " + "x" * 50}},
                    text_chars=20)
    assert ref["ids"] == ["11.C3.MR4", "2422/QĐ-BGDĐT"] and len(ref["text"]) == 20 and ref["score"] == 0.42
