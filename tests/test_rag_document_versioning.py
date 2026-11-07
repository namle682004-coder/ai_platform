"""
A new version of a document replaces the old one (survey requirements #11 / #22: the bot must never answer
from a version that was replaced). The old version stays searchable until the new one is indexed, so a
replacement still being parsed, or failing to parse, never leaves the knowledge base without the document.
"""

import asyncio

import pytest

from solutions.rag.application.use_cases.ingestion_use_case import DocumentIngestionUseCase
from solutions.rag.application.use_cases.knowledge_use_case import KnowledgeManagementUseCase


class FakeDocRepo:
    def __init__(self):
        self.docs = {}

    async def get_document(self, doc_id: str):
        return dict(self.docs[doc_id]) if doc_id in self.docs else None

    async def create_document(self, doc: dict):
        self.docs[doc["doc_id"]] = dict(doc)
        return doc["doc_id"]

    async def update_document_status(self, doc_id: str, status: str, details: dict = None):
        if doc_id not in self.docs:
            return False
        self.docs[doc_id]["status"] = status
        self.docs[doc_id].update(details or {})
        return True

    async def find_by_content_hash(self, tenant_id: str, content_hash: str):
        return [d for d in self.docs.values() if d.get("content_sha256") == content_hash]


class FakeStorage:
    def upload_bytes(self, bucket, object_name, data):
        return f"s3://{bucket}/{object_name}"


class FakeIndex:
    """Vector store and table store: what a document still has in retrieval."""

    def __init__(self):
        self.deleted_passages, self.deleted_tables = [], []

    async def delete_by_doc_id(self, doc_id, tenant_id):
        self.deleted_passages.append((doc_id, tenant_id))
        return True

    async def delete_document(self, tenant_id, doc_id):
        self.deleted_tables.append((tenant_id, doc_id))
        return 1


def _setup():
    repo, index = FakeDocRepo(), FakeIndex()
    knowledge = KnowledgeManagementUseCase(doc_repo=repo, storage=FakeStorage(), vector_store=index)
    ingestion = DocumentIngestionUseCase.__new__(DocumentIngestionUseCase)
    ingestion.doc_repo, ingestion.vector_store, ingestion.table_store = repo, index, index
    return repo, index, knowledge, ingestion


def test_the_old_version_is_retired_only_once_the_new_one_is_indexed():
    async def run():
        repo, index, knowledge, ingestion = _setup()
        v1 = await knowledge.upload_document(b"HDSD v1", "HDSD_v1.docx", title="Hướng dẫn sử dụng", tenant_id="t_dvkh")
        await repo.update_document_status(v1["doc_id"], "INDEXED")
        v2 = await knowledge.upload_document("HDSD v2, có chức năng mới".encode(), "HDSD_v2.docx", tenant_id="t_dvkh",
                                             replaces_doc_id=v1["doc_id"])
        assert v2["version"] == 2 and v2["replaces_doc_id"] == v1["doc_id"] and v2["title"] == "Hướng dẫn sử dụng"
        # While v2 waits for (or goes through) ingestion, v1 still answers.
        assert repo.docs[v1["doc_id"]]["status"] == "INDEXED" and not index.deleted_passages

        assert await ingestion.retire_replaced(v1["doc_id"], v2["doc_id"], "t_dvkh")
        old = repo.docs[v1["doc_id"]]
        assert old["status"] == "SUPERSEDED" and old["effective_status"] == "SUPERSEDED"
        assert old["superseded_by"] == v2["doc_id"]
        assert index.deleted_passages == [(v1["doc_id"], "t_dvkh")]
        assert index.deleted_tables == [("t_dvkh", v1["doc_id"])]
        assert not await ingestion.retire_replaced(v1["doc_id"], v2["doc_id"], "t_dvkh")  # once only

    asyncio.run(run())


def test_a_replacement_that_fails_to_index_leaves_the_old_version_in_place():
    async def run():
        repo, index, knowledge, _ingestion = _setup()
        v1 = await knowledge.upload_document(b"HDSD v1", "HDSD_v1.docx", tenant_id="t_dvkh")
        await repo.update_document_status(v1["doc_id"], "INDEXED")
        v2 = await knowledge.upload_document(b"tep loi", "HDSD_v2.docx", tenant_id="t_dvkh",
                                             replaces_doc_id=v1["doc_id"])
        await repo.update_document_status(v2["doc_id"], "FAILED", {"error": "parse error"})  # ingestion failed
        assert repo.docs[v1["doc_id"]]["status"] == "INDEXED" and not index.deleted_passages

    asyncio.run(run())


def test_a_document_of_another_tenant_cannot_be_replaced():
    async def run():
        repo, index, knowledge, ingestion = _setup()
        other = await knowledge.upload_document(b"tai lieu B", "b.docx", tenant_id="t_other")
        with pytest.raises(ValueError):
            await knowledge.upload_document(b"tai lieu A", "a.docx", tenant_id="t_dvkh", replaces_doc_id=other["doc_id"])
        assert not await ingestion.retire_replaced(other["doc_id"], "doc_x", "t_dvkh")
        assert repo.docs[other["doc_id"]]["status"] == "PENDING" and not index.deleted_passages

    asyncio.run(run())
