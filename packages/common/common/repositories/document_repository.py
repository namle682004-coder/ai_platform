from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from common.database.mongodb import mongo_manager

logger = logging.getLogger(__name__)


class MongoDocumentRepository:
    """MongoDB Atlas repository for RAG Enterprise Documents & Knowledge Base."""

    _doc_cache: Dict[str, Dict[str, Any]] = {}

    def __init__(self) -> None:
        pass

    def get_db(self):
        return mongo_manager.get_database()

    async def create_document(self, doc_record: Dict[str, Any]) -> Dict[str, Any]:
        """Insert a newly queued document record."""
        now = datetime.now(timezone.utc).isoformat()
        doc_record.setdefault("created_at", now)
        doc_record.setdefault("updated_at", now)
        doc_record.setdefault("status", "QUEUED")
        doc_record.setdefault("total_chunks", 0)
        doc_record.setdefault("allowed_roles", ["*"])  # Default accessible to all tenant roles

        db = self.get_db()
        if db is not None:
            try:
                await db.rag_documents.insert_one(dict(doc_record))
            except Exception as e:
                logger.warning(f"Failed to persist document to MongoDB: {e}")

        clean = dict(doc_record)
        clean.pop("_id", None)
        self._doc_cache[clean["doc_id"]] = clean
        return clean

    async def get_document(self, doc_id: str, tenant_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Retrieve a document by ID with optional tenant isolation check."""
        query: Dict[str, Any] = {"doc_id": doc_id}
        if tenant_id:
            query["tenant_id"] = tenant_id

        db = self.get_db()
        if db is not None:
            try:
                doc = await db.rag_documents.find_one(query, {"_id": 0})
                if doc:
                    self._doc_cache[doc_id] = doc
                    return doc
            except Exception as e:
                logger.warning(f"Failed to read document from MongoDB: {e}")

        cached = self._doc_cache.get(doc_id)
        if cached and (not tenant_id or cached.get("tenant_id") == tenant_id):
            return cached
        return None

    async def list_documents(
        self,
        tenant_id: str,
        skip: int = 0,
        limit: int = 50,
        status: Optional[str] = None,
        department: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """List documents belonging to a tenant with optional status/department filters."""
        query: Dict[str, Any] = {"tenant_id": tenant_id}
        if status:
            query["status"] = status
        if department:
            query["department"] = department

        db = self.get_db()
        if db is not None:
            try:
                cursor = db.rag_documents.find(query, {"_id": 0}).sort("created_at", -1).skip(skip).limit(limit)
                return await cursor.to_list(length=limit)
            except Exception as e:
                logger.warning(f"Failed to list documents from MongoDB: {e}")

        # Fallback cache
        matches = [
            d for d in self._doc_cache.values()
            if d.get("tenant_id") == tenant_id
            and (not status or d.get("status") == status)
            and (not department or d.get("department") == department)
        ]
        return matches[skip : skip + limit]

    async def count_documents(self, tenant_id: str, status: Optional[str] = None) -> int:
        """Count total documents for pagination."""
        query: Dict[str, Any] = {"tenant_id": tenant_id}
        if status:
            query["status"] = status

        db = self.get_db()
        if db is not None:
            try:
                return await db.rag_documents.count_documents(query)
            except Exception as e:
                logger.warning(f"Failed to count documents in MongoDB: {e}")

        return len([d for d in self._doc_cache.values() if d.get("tenant_id") == tenant_id])

    async def update_document_status(
        self,
        doc_id: str,
        status: str,
        updates: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Update document processing state and metrics."""
        now = datetime.now(timezone.utc).isoformat()
        payload: Dict[str, Any] = {
            "status": status,
            "updated_at": now,
        }
        if updates:
            payload.update(updates)

        db = self.get_db()
        if db is not None:
            try:
                await db.rag_documents.update_one({"doc_id": doc_id}, {"$set": payload})
            except Exception as e:
                logger.warning(f"Failed to update document status in MongoDB: {e}")

        if doc_id in self._doc_cache:
            self._doc_cache[doc_id].update(payload)
            return self._doc_cache[doc_id]
        return None

    async def delete_document(self, doc_id: str, tenant_id: Optional[str] = None) -> bool:
        """Delete document record by ID."""
        query: Dict[str, Any] = {"doc_id": doc_id}
        if tenant_id:
            query["tenant_id"] = tenant_id

        deleted_in_db = False
        db = self.get_db()
        if db is not None:
            try:
                result = await db.rag_documents.delete_many(query)
                deleted_in_db = result.deleted_count > 0
            except Exception as e:
                logger.warning(f"Failed to delete document from MongoDB: {e}")

        was_cached = doc_id in self._doc_cache
        self._doc_cache.pop(doc_id, None)
        return deleted_in_db or was_cached

    async def record_feedback(self, feedback: Dict[str, Any]) -> Dict[str, Any]:
        """Record user feedback (thumbs up/down, citation accuracy) for RAG audit."""
        feedback.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
        db = self.get_db()
        if db is not None:
            try:
                await db.rag_feedback.insert_one(dict(feedback))
            except Exception as e:
                logger.warning(f"Failed to log feedback: {e}")
        return feedback


document_repository = MongoDocumentRepository()
