"""
Uploading the same file twice into one knowledge base (two accounts of a project, or a retry) must not
index it twice: every passage would come back twice in retrieval, as duplicate sources [1] and [2].
"""

import asyncio
from typing import Any, Dict, List, Optional

from solutions.rag.application.use_cases.knowledge_use_case import KnowledgeManagementUseCase
from solutions.rag.domain.ports import DocumentRepositoryPort

FILE = b"%PDF-1.4 same bytes"


class MemoryRepo(DocumentRepositoryPort):
    def __init__(self):
        self.docs: Dict[str, Dict[str, Any]] = {}

    async def get_document(self, doc_id: str) -> Optional[Dict[str, Any]]:
        return self.docs.get(doc_id)

    async def create_document(self, doc_data: Dict[str, Any]) -> str:
        self.docs[doc_data["doc_id"]] = dict(doc_data)
        return doc_data["doc_id"]

    async def update_document_status(self, doc_id, status, details=None) -> bool:
        self.docs[doc_id]["status"] = status
        return True

    async def list_documents(self, tenant_id, department=None, page=1, page_size=20, status=None):
        items = [d for d in self.docs.values() if d["tenant_id"] == tenant_id]
        return items, len(items)

    async def delete_document(self, doc_id: str, tenant_id: str) -> bool:
        return self.docs.pop(doc_id, None) is not None

    async def find_by_content_hash(self, tenant_id: str, content_sha256: str) -> List[Dict[str, Any]]:
        return [d for d in self.docs.values() if d["tenant_id"] == tenant_id and d.get("content_sha256") == content_sha256]


class Storage:
    def __init__(self):
        self.uploads: List[str] = []

    def upload_bytes(self, bucket, object_name, data):
        self.uploads.append(object_name)
        return f"s3://{bucket}/{object_name}"


def _uc():
    repo, storage = MemoryRepo(), Storage()
    return KnowledgeManagementUseCase(doc_repo=repo, storage=storage, vector_store=None, embedding_service=None), repo, storage


def _upload(uc, tenant="proj_a", roles=None, data=FILE, name="ban_tin.pdf"):
    return asyncio.run(uc.upload_document(file_bytes=data, filename=name, tenant_id=tenant, allowed_roles=roles))


def test_same_file_in_same_tenant_returns_the_existing_document():
    uc, repo, storage = _uc()
    first = _upload(uc)
    second = _upload(uc, name="ban_tin (1).pdf")  # renamed copy, same bytes
    assert second["deduplicated"] and second["doc_id"] == first["doc_id"]
    assert len(repo.docs) == 1 and len(storage.uploads) == 1
    assert first["content_sha256"] and not first.get("deduplicated")


def test_other_tenant_or_other_audience_or_other_bytes_is_a_separate_document():
    uc, repo, _ = _uc()
    _upload(uc)
    assert not _upload(uc, tenant="proj_b").get("deduplicated")  # another knowledge base
    assert not _upload(uc, roles=["hr"]).get("deduplicated")  # restricted to other roles
    assert not _upload(uc, data=FILE + b" v2").get("deduplicated")  # a new version
    assert len(repo.docs) == 4


def test_failed_upload_can_be_retried():
    uc, repo, _ = _uc()
    first = _upload(uc)
    repo.docs[first["doc_id"]]["status"] = "FAILED"
    retry = _upload(uc)
    assert not retry.get("deduplicated") and retry["doc_id"] != first["doc_id"]
