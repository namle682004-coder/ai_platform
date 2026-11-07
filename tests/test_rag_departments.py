"""
Questions scoped to a department (survey requirement #12: DVKH and service management follow different
procedures). Departments come from the tenant's own documents; a question for a department sees that
department's documents and the shared ones, never only one or the other.
"""

import asyncio

from solutions.rag.domain.entities import SHARED_DEPARTMENT
from solutions.rag.infrastructure.adapters.qdrant_adapter import QdrantVectorStoreAdapter
from solutions.rag.infrastructure.repositories.mongo_document_repo import MongoDocumentRepositoryAdapter


def _department_condition(conditions):
    return next((c for c in conditions if c.get("key") == "department"), None)


def test_a_department_question_also_sees_the_shared_documents():
    cond = _department_condition(QdrantVectorStoreAdapter._build_filter_conditions("t1", department="Phòng A"))
    assert cond == {"key": "department", "match": {"any": sorted({"Phòng A", SHARED_DEPARTMENT})}}
    # No department chosen: every document of the tenant (no department condition at all).
    assert _department_condition(QdrantVectorStoreAdapter._build_filter_conditions("t1")) is None


def test_departments_are_listed_from_the_documents_still_in_use():
    repo = MongoDocumentRepositoryAdapter(mongo_uri="mongodb://127.0.0.1:1/none?serverSelectionTimeoutMS=50")
    repo._memory_docs = {
        "d1": {"tenant_id": "t1", "department": "Phòng A", "status": "INDEXED"},
        "d2": {"tenant_id": "t1", "department": "Phòng B", "status": "INDEXED"},
        "d3": {"tenant_id": "t1", "department": SHARED_DEPARTMENT, "status": "INDEXED"},
        "d4": {"tenant_id": "t2", "department": "Phòng khác tenant", "status": "INDEXED"},
        "d5": {"tenant_id": "t1", "department": "Phòng cũ", "status": "SUPERSEDED"},
        "d6": {"tenant_id": "t1", "department": "Phòng lỗi", "status": "FAILED"},
    }
    assert asyncio.run(repo.list_departments("t1")) == sorted(["Phòng A", "Phòng B", SHARED_DEPARTMENT])
