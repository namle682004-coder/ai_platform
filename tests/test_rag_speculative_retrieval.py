"""
Latency: the search + rerank of a first message runs during the analysis LLM call and is reused when the
analyzer keeps the question; it is discarded (cancelled) for support turns and for rewritten questions.
"""

import asyncio

import pytest

from solutions.rag.application.dtos import RagChatRequestDTO
from test_rag_answer_pipeline import ScriptedLLM, ScoreReranker, _use_case


class CountingReranker(ScoreReranker):
    def __init__(self):
        self.queries = []

    async def arerank(self, query, candidates, top_n=5, min_threshold=0.0):
        self.queries.append((query, len(candidates)))
        return await super().arerank(query, candidates, top_n, min_threshold)


@pytest.fixture(autouse=True)
def _speculation_on(monkeypatch):
    # Off by default (single shared GPU deployments); these tests turn it on.
    from solutions.rag.config import rag_settings

    monkeypatch.setattr(rag_settings, "speculative_retrieval_enabled", True)


def _run(analysis, query, answer="Mỗi năm có 12 ngày phép theo HR.A2.1 [1]."):
    uc, store, repo = _use_case(ScriptedLLM(analysis, answer))
    uc.reranker_service = CountingReranker()
    resp = asyncio.run(uc.execute(RagChatRequestDTO(query=query, similarity_threshold=0.0)))
    return resp, store, uc.reranker_service


def test_first_question_reuses_the_search_made_during_analysis():
    q = "Mỗi năm có bao nhiêu ngày phép?"
    resp, store, reranker = _run({"intent": "document_question", "standalone_query": q}, q)
    assert "12 ngày phép" in resp.answer
    # One search (its BM25 text carries the unaccented form too), made during analysis, not repeated.
    assert len(store.queries) == 1 and store.queries[0].startswith(q)
    assert len(reranker.queries) == 1 and reranker.queries[0][0] == q


def test_a_corrected_question_still_counts_as_the_same_question():
    # The analyzer restored an accent / fixed a word: same question, the early search is kept.
    resp, store, _ = _run({"intent": "document_question", "standalone_query": "Mỗi năm có bao nhiêu ngày phép vậy?"},
                          "Mỗi năm có bao nhiêu ngày phép?")
    assert len(store.queries) == 1


def test_a_rewritten_question_is_searched_again():
    resp, store, _ = _run({"intent": "document_question", "standalone_query": "Quy định làm việc từ xa tối đa mấy ngày?"},
                          "Thế còn WFH?")
    assert store.queries[0].startswith("Thế còn WFH?")
    assert any(s.startswith("Quy định làm việc từ xa tối đa mấy ngày?") for s in store.queries[1:])


def test_a_support_turn_cancels_the_early_search():
    resp, store, reranker = _run({"intent": "support_request"}, "Cho tôi gặp nhân viên hỗ trợ")
    assert resp.intent == "ESCALATION"
    assert len(reranker.queries) <= 1  # at most the cancelled early pass; nothing after the routing decision
