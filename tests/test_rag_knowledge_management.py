"""
Knowledge-base behaviour of the standalone RAG service that was merged in from the former
gateway knowledge API: legacy records, upload wait, tenant-safe delete.
"""

import asyncio
from datetime import datetime, timezone

from solutions.rag.application.use_cases.knowledge_use_case import (
    KnowledgeManagementUseCase,
    _iso_timestamp,
    _title_from_filename,
)
from solutions.rag.infrastructure.repositories.mongo_document_repo import _tenant_filter


class FakeDocRepo:
    def __init__(self, docs):
        self.docs = {d["doc_id"]: dict(d) for d in docs}
        self.deleted = []

    async def get_document(self, doc_id):
        return self.docs.get(doc_id)

    async def delete_document(self, doc_id, tenant_id):
        self.deleted.append((doc_id, tenant_id))
        return self.docs.pop(doc_id, None) is not None


class FakeStorage:
    def __init__(self):
        self.deleted = []

    def delete_object(self, bucket, object_name):
        self.deleted.append((bucket, object_name))


class FakeVectorStore:
    def __init__(self):
        self.deleted = []

    async def delete_by_doc_id(self, doc_id, tenant_id):
        self.deleted.append((doc_id, tenant_id))


def _use_case(docs):
    return KnowledgeManagementUseCase(doc_repo=FakeDocRepo(docs), storage=FakeStorage(), vector_store=FakeVectorStore())


def test_iso_timestamp_accepts_epoch_iso_and_datetime():
    assert _iso_timestamp(0) == "1970-01-01T00:00:00Z"
    # Format written by the former gateway knowledge API
    assert _iso_timestamp("2026-11-03T08:15:00.123456+00:00") == "2026-11-03T08:15:00Z"
    assert _iso_timestamp("2026-11-03T08:15:00Z") == "2026-11-03T08:15:00Z"
    assert _iso_timestamp(datetime(2026, 11, 3, 8, 15, tzinfo=timezone.utc)) == "2026-11-03T08:15:00Z"


def test_title_from_filename():
    assert _title_from_filename("so_tay-nhan_vien.pdf") == "so tay nhan vien"


def test_default_tenant_matches_legacy_global_records():
    match = _tenant_filter("proj_default")
    assert "global" in match["$in"] and "proj_default" in match["$in"]
    assert _tenant_filter("global") == match
    assert _tenant_filter("proj_alpha") == "proj_alpha"


def test_get_document_with_legacy_iso_timestamps():
    uc = _use_case([{
        "doc_id": "doc_legacy",
        "tenant_id": "global",
        "status": "QUEUED",
        "created_at": "2026-10-01T10:00:00+00:00",
        "updated_at": "2026-10-01T10:00:05+00:00",
    }])
    dto = asyncio.run(uc.get_document("doc_legacy"))
    assert dto.created_at == "2026-10-01T10:00:00Z"
    assert dto.updated_at == "2026-10-01T10:00:05Z"


def test_delete_refuses_other_tenants_document():
    uc = _use_case([{"doc_id": "doc_b", "tenant_id": "proj_beta", "s3_object_name": "documents/proj_beta/doc_b.pdf"}])

    assert asyncio.run(uc.delete_document("doc_b", tenant_id="proj_alpha")) is False
    assert uc.storage.deleted == []
    assert uc.vector_store.deleted == []
    assert "doc_b" in uc.doc_repo.docs


def test_delete_shared_kb_document_stored_as_global():
    uc = _use_case([{"doc_id": "doc_g", "tenant_id": "global", "s3_bucket": "aip-data", "s3_object_name": "knowledge/global/doc_g.txt"}])

    assert asyncio.run(uc.delete_document("doc_g", tenant_id="proj_default")) is True
    assert uc.vector_store.deleted == [("doc_g", "proj_default")]
    assert uc.storage.deleted == [("aip-data", "knowledge/global/doc_g.txt")]


def test_wait_for_indexing_returns_once_worker_finishes():
    uc = _use_case([{"doc_id": "doc_w", "tenant_id": "proj_alpha", "status": "PROCESSING"}])

    async def _run():
        async def worker():
            await asyncio.sleep(0.05)
            uc.doc_repo.docs["doc_w"]["status"] = "INDEXED"
            uc.doc_repo.docs["doc_w"]["total_chunks"] = 7

        asyncio.create_task(worker())
        return await uc.wait_for_indexing("doc_w", timeout_seconds=2.0, poll_interval=0.01)

    dto = asyncio.run(_run())
    assert dto.status == "INDEXED"
    assert dto.total_chunks == 7


def test_wait_for_indexing_gives_up_after_timeout():
    uc = _use_case([{"doc_id": "doc_slow", "tenant_id": "proj_alpha", "status": "PENDING"}])
    dto = asyncio.run(uc.wait_for_indexing("doc_slow", timeout_seconds=0.05, poll_interval=0.01))
    assert dto.status == "PENDING"
