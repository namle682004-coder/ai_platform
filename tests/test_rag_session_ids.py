"""
Conversation ids in URLs are opaque (/c/{uuid}): new conversations get a random UUID, older ones with
readable ids ("sess_<time>_<rand>") are shown as a hash the API resolves. Citations carry the source's
format so a cited Word file opens as Word, not as extracted text.
"""

import asyncio
import uuid
from types import SimpleNamespace

from solutions.rag.application.components.prompt_builder import prompt_builder
from solutions.rag.application.components.session_ids import (
    match_public_id, new_session_id, public_session_id,
)
from solutions.rag.application.use_cases.chat_use_case import _build_citation_dto
from solutions.rag.application.use_cases.session_use_case import RagSessionUseCase

LEGACY = "sess_mw4gfuwi_cozr"


def test_new_conversation_ids_are_random_uuids():
    a, b = new_session_id(), new_session_id()
    assert uuid.UUID(a).version == 4 and a != b
    assert public_session_id(a) == a  # nothing to hide: shown as it is


def test_older_ids_are_shown_as_a_stable_hash_and_resolved_back():
    public = public_session_id(LEGACY)
    assert uuid.UUID(public).version == 5 and LEGACY not in public and "mw4gfuwi" not in public
    assert public == public_session_id(LEGACY)  # same link every time
    assert public_session_id(LEGACY.upper()) != public
    assert match_public_id(public.upper(), ["sess_other", LEGACY]) == LEGACY
    assert match_public_id("not-a-uuid", [LEGACY]) is None


class Repo:
    def __init__(self, records):
        self.records = {r["session_id"]: r for r in records}

    async def get_session(self, session_id, user_id, tenant_id):
        return self.records.get(session_id)

    async def list_sessions(self, user_id, tenant_id, limit=50):
        return [{"session_id": sid, "title": r["title"], "updated_at": 1.0} for sid, r in self.records.items()][:limit]


def _record(sid):
    return {"session_id": sid, "title": "t", "messages": [
        {"message_id": "msg_1", "role": "assistant", "content": "x", "timestamp": 1.0,
         "citations": [{"index": 1, "doc_id": "doc_1", "title": "mxh daklak", "file_type": "docx"}]}]}


def test_sessions_list_and_open_by_public_id():
    fresh = new_session_id()
    uc = RagSessionUseCase(Repo([_record(LEGACY), _record(fresh)]))
    listed = asyncio.run(uc.list_sessions("u", "t")).items
    assert {i.session_id: i.public_id for i in listed} == {LEGACY: public_session_id(LEGACY), fresh: fresh}

    by_hash = asyncio.run(uc.get_session(public_session_id(LEGACY), "u", "t"))
    assert by_hash.session_id == LEGACY and by_hash.public_id == public_session_id(LEGACY)
    assert by_hash.messages[0].citations[0].file_type == "docx"  # reopened history keeps the format
    assert asyncio.run(uc.get_session(fresh, "u", "t")).public_id == fresh
    assert asyncio.run(uc.get_session(str(uuid.uuid4()), "u", "t")) is None


def test_citations_carry_the_format_of_their_document():
    chunk = SimpleNamespace(text="Đoàn kiểm tra số 523 làm việc với xã Tam Giang.", doc_id="doc_1", title="mxh daklak",
                            page_number=5, score=0.9, chunk_index=3,
                            metadata={"file_type": "docx", "content_type": "text", "chunk_id": "c3"})
    citations, _ = prompt_builder.extract_citations_and_blocks([chunk], query="Đoàn kiểm tra")
    assert citations[0]["file_type"] == "docx" and citations[0]["content_type"] == "text"
    assert _build_citation_dto(citations[0]).file_type == "docx"
