"""
MongoDB Document Repository Adapter for AIP Enterprise RAG Solution.
Implements domain DocumentRepositoryPort.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, List, Optional, Tuple

from motor.motor_asyncio import AsyncIOMotorClient
from ...domain.entities import DEFAULT_TENANT_ID, FALLBACK_TENANT_ALIASES, normalize_tenant_id
from ...domain.ports import DocumentRepositoryPort

logger = logging.getLogger("aip-rag.repo.mongo_document")


def _tenant_filter(tenant_id: str) -> Any:
    """
    Mongo match for a tenant. Records written by the former gateway knowledge API stored the
    shared knowledge base as 'global' (and other legacy aliases), so the canonical default
    tenant must match those as well.
    """
    tenant_id = normalize_tenant_id(tenant_id)
    if tenant_id == DEFAULT_TENANT_ID:
        return {"$in": sorted(FALLBACK_TENANT_ALIASES | {DEFAULT_TENANT_ID})}
    return tenant_id


class MongoDocumentRepositoryAdapter(DocumentRepositoryPort):
    """MongoDB implementation of DocumentRepositoryPort."""

    def __init__(self, mongo_uri: Optional[str] = None) -> None:
        self.mongo_uri = mongo_uri or os.getenv("MONGO_URI") or os.getenv("MONGODB_URI") or ""
        self._client: Optional[AsyncIOMotorClient] = None
        self._memory_docs: Dict[str, Dict[str, Any]] = {}
        self._hash_index_ready = False

    def _get_collection(self) -> Any:
        if self._client is None:
            self._client = AsyncIOMotorClient(self.mongo_uri)
        db_name = self.mongo_uri.split("/")[-1].split("?")[0] or "ai_platform"
        return self._client[db_name]["rag_documents"]

    async def get_document(self, doc_id: str) -> Optional[Dict[str, Any]]:
        try:
            coll = self._get_collection()
            doc = await coll.find_one({"doc_id": doc_id})
            if doc:
                doc.pop("_id", None)
                return doc
        except Exception as exc:
            logger.debug("Mongo get_document fallback (%s)", exc)

        return self._memory_docs.get(doc_id)

    async def create_document(self, doc_data: Dict[str, Any]) -> str:
        doc_id = doc_data["doc_id"]
        self._memory_docs[doc_id] = dict(doc_data)

        try:
            coll = self._get_collection()
            await coll.update_one({"doc_id": doc_id}, {"$set": doc_data}, upsert=True)
        except Exception as exc:
            logger.warning("Mongo create_document fallback (%s)", exc)

        return doc_id

    async def update_document_status(
        self,
        doc_id: str,
        status: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> bool:
        now = int(time.time())
        update_fields: Dict[str, Any] = {"status": status, "updated_at": now}
        if details:
            update_fields.update(details)

        if doc_id in self._memory_docs:
            self._memory_docs[doc_id].update(update_fields)

        try:
            coll = self._get_collection()
            res = await coll.update_one({"doc_id": doc_id}, {"$set": update_fields})
            return res.modified_count > 0
        except Exception as exc:
            logger.warning("Mongo update_document_status fallback (%s)", exc)
            return True

    async def list_documents(
        self,
        tenant_id: str,
        department: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
        status: Optional[str] = None,
    ) -> Tuple[List[Dict[str, Any]], int]:
        query: Dict[str, Any] = {"tenant_id": _tenant_filter(tenant_id)}
        if department:
            query["department"] = department
        if status:
            query["status"] = status

        skip = (page - 1) * page_size
        items: List[Dict[str, Any]] = []
        total = 0

        try:
            coll = self._get_collection()
            total = await coll.count_documents(query)
            cursor = coll.find(query).sort("created_at", -1).skip(skip).limit(page_size)
            async for doc in cursor:
                doc.pop("_id", None)
                items.append(doc)
            return items, total
        except Exception as exc:
            logger.debug("Mongo list_documents fallback (%s)", exc)

        # In-memory fallback
        tenant_id = normalize_tenant_id(tenant_id)
        matched = [d for d in self._memory_docs.values() if normalize_tenant_id(d.get("tenant_id")) == tenant_id]
        if department:
            matched = [d for d in matched if d.get("department") == department]
        if status:
            matched = [d for d in matched if d.get("status") == status]
        total = len(matched)
        items = matched[skip : skip + page_size]
        return items, total

    async def find_by_content_hash(self, tenant_id: str, content_sha256: str) -> List[Dict[str, Any]]:
        if not content_sha256:
            return []
        try:
            coll = self._get_collection()
            if not self._hash_index_ready:
                await coll.create_index([("tenant_id", 1), ("content_sha256", 1)], name="tenant_content_sha256")
                self._hash_index_ready = True
            cursor = coll.find(
                {"tenant_id": _tenant_filter(tenant_id), "content_sha256": content_sha256}
            ).sort("created_at", 1)
            out: List[Dict[str, Any]] = []
            async for doc in cursor:
                doc.pop("_id", None)
                out.append(doc)
            return out
        except Exception as exc:
            logger.debug("Mongo find_by_content_hash fallback (%s)", exc)
        tenant_id = normalize_tenant_id(tenant_id)
        return sorted(
            (
                dict(d) for d in self._memory_docs.values()
                if normalize_tenant_id(d.get("tenant_id")) == tenant_id and d.get("content_sha256") == content_sha256
            ),
            key=lambda d: d.get("created_at", 0),
        )

    async def find_by_source(self, tenant_id: str, source_id: str) -> List[Dict[str, Any]]:
        try:
            cursor = self._get_collection().find({"tenant_id": _tenant_filter(tenant_id), "source_id": source_id})
            return [{k: v for k, v in d.items() if k != "_id"} async for d in cursor]
        except Exception as exc:
            logger.debug("Mongo find_by_source fallback (%s)", exc)
        return [dict(d) for d in self._memory_docs.values()
                if d.get("source_id") == source_id and normalize_tenant_id(d.get("tenant_id")) == normalize_tenant_id(tenant_id)]

    async def list_departments(self, tenant_id: str) -> List[str]:
        """Departments of the tenant's documents (those still in use, not superseded or failed)."""
        query = {"tenant_id": _tenant_filter(tenant_id), "status": {"$nin": ["SUPERSEDED", "FAILED"]}}
        try:
            values = await self._get_collection().distinct("department", query)
        except Exception as exc:
            logger.debug("Mongo list_departments fallback (%s)", exc)
            values = [d.get("department") for d in self._memory_docs.values()
                      if normalize_tenant_id(d.get("tenant_id")) == normalize_tenant_id(tenant_id)
                      and d.get("status") not in ("SUPERSEDED", "FAILED")]
        return sorted({str(v).strip() for v in values if v and str(v).strip()})

    async def count_by_source(self, tenant_id: str) -> Dict[str, int]:
        """Number of documents of each connector source of a tenant."""
        try:
            pipeline = [{"$match": {"tenant_id": _tenant_filter(tenant_id), "source_id": {"$exists": True}}},
                        {"$group": {"_id": "$source_id", "n": {"$sum": 1}}}]
            return {d["_id"]: d["n"] async for d in self._get_collection().aggregate(pipeline)}
        except Exception as exc:
            logger.debug("Mongo count_by_source fallback (%s)", exc)
        counts: Dict[str, int] = {}
        for d in self._memory_docs.values():
            if d.get("source_id") and normalize_tenant_id(d.get("tenant_id")) == normalize_tenant_id(tenant_id):
                counts[d["source_id"]] = counts.get(d["source_id"], 0) + 1
        return counts

    async def delete_document(self, doc_id: str, tenant_id: str) -> bool:
        self._memory_docs.pop(doc_id, None)
        try:
            coll = self._get_collection()
            res = await coll.delete_one({"doc_id": doc_id, "tenant_id": _tenant_filter(tenant_id)})
            return res.deleted_count > 0
        except Exception as exc:
            logger.warning("Mongo delete_document fallback (%s)", exc)
            return True
