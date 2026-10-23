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
from ...domain.ports import DocumentRepositoryPort

logger = logging.getLogger("aip-rag.repo.mongo_document")


class MongoDocumentRepositoryAdapter(DocumentRepositoryPort):
    """MongoDB implementation of DocumentRepositoryPort."""

    def __init__(self, mongo_uri: Optional[str] = None) -> None:
        self.mongo_uri = mongo_uri or os.getenv("MONGO_URI") or os.getenv("MONGODB_URI") or ""
        self._client: Optional[AsyncIOMotorClient] = None
        self._memory_docs: Dict[str, Dict[str, Any]] = {}

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
    ) -> Tuple[List[Dict[str, Any]], int]:
        query: Dict[str, Any] = {"tenant_id": tenant_id}
        if department:
            query["department"] = department

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
        matched = [d for d in self._memory_docs.values() if d.get("tenant_id") == tenant_id]
        if department:
            matched = [d for d in matched if d.get("department") == department]
        total = len(matched)
        items = matched[skip : skip + page_size]
        return items, total

    async def delete_document(self, doc_id: str, tenant_id: str) -> bool:
        self._memory_docs.pop(doc_id, None)
        try:
            coll = self._get_collection()
            res = await coll.delete_one({"doc_id": doc_id, "tenant_id": tenant_id})
            return res.deleted_count > 0
        except Exception as exc:
            logger.warning("Mongo delete_document fallback (%s)", exc)
            return True
