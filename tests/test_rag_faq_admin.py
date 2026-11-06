"""
Admin-curated Q&A pairs: listed and edited per tenant, and answered verbatim when they clearly match.
"""

import asyncio
from types import SimpleNamespace
from typing import Any, Dict

from solutions.rag.application.use_cases.knowledge_use_case import KnowledgeManagementUseCase


class Embedder:
    async def get_embedding(self, text):
        return [0.1, 0.2]


class Vectors:
    """Qdrant stand-in keyed like the adapter: one point per (doc_id, chunk_index)."""

    def __init__(self):
        self.points: Dict[str, Dict[str, Any]] = {}

    async def upsert_chunks(self, chunks, vectors, tenant_id, title, filename=None, file_type=None, department=None,
                            allowed_roles=None):
        for c in chunks:
            self.points[f"{c.doc_id}_{c.chunk_index}"] = {
                "doc_id": c.doc_id, "tenant_id": tenant_id, "file_type": file_type, "title": title, "text": c.text,
                "created_at": 1, **c.metadata,
            }
        return len(chunks)

    async def list_faq_entries(self, tenant_id, limit=1000):
        rows = [p for p in self.points.values() if p["tenant_id"] == tenant_id and p["file_type"] == "faq"]
        return sorted(rows, key=lambda p: p.get("updated_at") or 0, reverse=True)

    async def delete_by_doc_id(self, doc_id, tenant_id):
        self.points = {k: v for k, v in self.points.items() if v["doc_id"] != doc_id}
        return True


def _uc():
    uc = KnowledgeManagementUseCase.__new__(KnowledgeManagementUseCase)
    uc.vector_store, uc.embedding_service = Vectors(), Embedder()

    async def no_cache(*a, **k):
        return None

    uc._invalidate_tenant_cache = no_cache
    return uc


def test_qa_pairs_are_listed_edited_in_place_and_deleted_per_tenant():
    uc = _uc()
    created = asyncio.run(uc.ingest_qa(question="Cách cài Plugin ký số?", answer="Bước 1: tải plugin…",
                                       category="Chữ ký số", tenant_id="proj_a",
                                       question_variations=["cai plugin ky so", "plugin ký số cài thế nào"]))
    asyncio.run(uc.ingest_qa(question="Hotline hỗ trợ?", answer="1900-xxxx", tenant_id="proj_b"))
    items = asyncio.run(uc.list_qa("proj_a"))
    assert [i["question"] for i in items] == ["Cách cài Plugin ký số?"]  # another project's pairs are not listed
    first = items[0]
    assert first["answer"] == "Bước 1: tải plugin…" and first["category"] == "Chữ ký số"
    assert first["question_variations"] == ["cai plugin ky so", "plugin ký số cài thế nào"]

    asyncio.run(uc.update_qa(created.qa_id, tenant_id="proj_a", question="Cách cài Plugin ký số?",
                             answer="Bước 1: tải plugin. Bước 2: chạy file cài đặt.", category="Chữ ký số"))
    items = asyncio.run(uc.list_qa("proj_a"))
    assert len(items) == 1 and items[0]["answer"].endswith("chạy file cài đặt.")  # same id: rewritten, not duplicated
    assert items[0]["created_at"] == first["created_at"]

    try:
        asyncio.run(uc.update_qa("qa_missing", tenant_id="proj_a", question="x?", answer="y"))
        raise AssertionError("editing a missing pair must fail")
    except KeyError:
        pass
    asyncio.run(uc.delete_qa(created.qa_id, tenant_id="proj_a"))
    assert asyncio.run(uc.list_qa("proj_a")) == []


def _faq_candidate(score):
    payload = {"doc_id": "qa_1", "qa_id": "qa_1", "file_type": "faq", "chunk_index": 0, "title": "FAQ: Hotline",
               "text": "[Hỏi - Đáp FAQ: general]\nCâu hỏi: Hotline hỗ trợ?\nTrả lời: Gọi 1900-xxxx nhánh 2.",
               "question": "Hotline hỗ trợ?", "question_variations": ["số điện thoại hỗ trợ"],
               "approved_answer": "Gọi **1900-xxxx** nhánh 2.", "page_number": 1}
    return {"id": "p1", "score": score, "payload": payload}


class PhrasingReranker:
    """Cross-encoder stand-in for question-vs-question scoring: a fixed score per stored phrasing."""

    def __init__(self, scores):
        self.scores, self.seen = scores, []

    async def arerank(self, query, candidates, top_n=5, min_threshold=0.0):
        self.seen += [c["payload"]["text"] for c in candidates]
        return [dict(c, score=self.scores.get(c["payload"]["text"], 0.0)) for c in candidates]


def _faq_plan():
    return SimpleNamespace(analysis=SimpleNamespace(challenge=False), standalone_query="Số hotline hỗ trợ là gì?",
                           kind="", intent="", answer="", direct_citations=[], context_chunks=[])


def test_a_clearly_matching_pair_is_answered_as_approved():
    from solutions.rag.application.components.context_selector import candidate_key
    from solutions.rag.application.use_cases.chat_use_case import RagChatUseCase

    uc = RagChatUseCase.__new__(RagChatUseCase)
    uc.reranker_service = PhrasingReranker({})
    strong, weak = _faq_candidate(0.93), _faq_candidate(0.41)
    p = _faq_plan()
    assert asyncio.run(uc._plan_faq_answer(p, [strong], {candidate_key(strong): 0.93}))
    assert p.intent == "QA_FAQ" and p.answer == "Gọi **1900-xxxx** nhánh 2." and p.direct_citations == []  # verbatim, no source
    assert not asyncio.run(uc._plan_faq_answer(_faq_plan(), [weak], {candidate_key(weak): 0.41}))  # a loose match
    doc = {"id": "d", "score": 0.95, "payload": {"doc_id": "doc_1", "file_type": "docx", "text": "Quy trình…"}}
    assert not asyncio.run(uc._plan_faq_answer(_faq_plan(), [doc], {candidate_key(doc): 0.95}))


def test_a_pair_matches_by_its_phrasings_not_its_answer():
    # The whole pair scores low (its answer reads like "not available"), yet the question is one of its
    # stored phrasings: question-to-question, it is the same question.
    from solutions.rag.application.components.context_selector import candidate_key
    from solutions.rag.application.use_cases.chat_use_case import RagChatUseCase

    uc = RagChatUseCase.__new__(RagChatUseCase)
    uc.reranker_service = PhrasingReranker({"so dien thoai ho tro": 0.91})
    pair = _faq_candidate(0.4)
    doc = {"id": "d", "score": 0.5, "payload": {"doc_id": "doc_1", "file_type": "docx", "text": "Bản tin…"}}
    p = _faq_plan()
    assert asyncio.run(uc._plan_faq_answer(p, [doc, pair], {candidate_key(pair): 0.4, candidate_key(doc): 0.5}))
    assert p.intent == "QA_FAQ"
    assert {"Hotline hỗ trợ?", "số điện thoại hỗ trợ", "so dien thoai ho tro"} <= set(uc.reranker_service.seen)


def test_the_unaccented_form_of_each_phrasing_is_indexed():
    uc = _uc()
    asyncio.run(uc.ingest_qa(question="Giá vé xe buýt Buôn Ma Thuột?", answer="Không có trong bản tin.", tenant_id="proj_a"))
    text = next(iter(uc.vector_store.points.values()))["text"]
    assert "Gia ve xe buyt Buon Ma Thuot?" in text
    items = asyncio.run(uc.list_qa("proj_a"))
    assert items[0]["question_variations"] == []  # what the admin typed is unchanged in the editor
