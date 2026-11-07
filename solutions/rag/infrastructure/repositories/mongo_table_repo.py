"""
MongoDB store of the whole tables of indexed documents (collection `rag_tables`), one record per table.
Tenancy and role filtering follow the vector store: the caller's tenant plus the configured shared knowledge
base, and `allowed_roles` containing '*' or the caller's role.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from motor.motor_asyncio import AsyncIOMotorClient

from ...config import rag_settings
from ...domain.ports import TableStorePort

logger = logging.getLogger("aip-rag.repo.mongo_tables")


def tenant_variants(tenant_id: str) -> List[str]:
    """Same tenancy rule as the vector store filter (QdrantVectorStoreAdapter._build_filter_conditions)."""
    tid = (tenant_id or "global").strip()
    shared = [t.strip() for t in (rag_settings.shared_kb_tenants or "").split(",") if t.strip()]
    if tid.lower() in ("global", "proj_default", "system", "*"):
        return list(dict.fromkeys(["global", "proj_default", *shared]))
    return list(dict.fromkeys([tid, tid.upper(), tid.lower(), *shared]))


class MongoTableStore(TableStorePort):
    def __init__(self, mongo_uri: Optional[str] = None) -> None:
        self.mongo_uri = mongo_uri or rag_settings.mongo_uri
        self._client: Optional[AsyncIOMotorClient] = None
        self._indexed = False

    async def _coll(self) -> Any:
        if self._client is None:
            self._client = AsyncIOMotorClient(self.mongo_uri)
        db_name = self.mongo_uri.split("/")[-1].split("?")[0] or "ai_platform"
        coll = self._client[db_name]["rag_tables"]
        if not self._indexed:
            await coll.create_index([("tenant_id", 1), ("doc_id", 1)], name="tenant_doc")
            await coll.create_index([("tenant_id", 1), ("signature", 1)], name="tenant_signature")
            self._indexed = True
        return coll

    async def replace_document(self, tenant_id: str, doc_id: str, allowed_roles: List[str],
                               tables: List[Dict[str, Any]]) -> int:
        coll = await self._coll()
        await coll.delete_many({"tenant_id": tenant_id, "doc_id": doc_id})
        if not tables:
            return 0
        docs = [{**t, "tenant_id": tenant_id, "doc_id": doc_id, "allowed_roles": allowed_roles or ["*"]} for t in tables]
        await coll.insert_many(docs)
        return len(docs)

    async def delete_document(self, tenant_id: str, doc_id: str) -> int:
        coll = await self._coll()
        res = await coll.delete_many({"tenant_id": {"$in": tenant_variants(tenant_id)}, "doc_id": doc_id})
        return res.deleted_count

    async def list_tables(self, tenant_id: str, user_role: str = "user", doc_ids: Optional[List[str]] = None,
                          signatures: Optional[List[str]] = None, limit: int = 500) -> List[Dict[str, Any]]:
        query: Dict[str, Any] = {
            "tenant_id": {"$in": tenant_variants(tenant_id)},
            "allowed_roles": {"$in": ["*", user_role]},
        }
        if doc_ids:
            query["doc_id"] = {"$in": list(doc_ids)}
        if signatures:
            query["signature"] = {"$in": list(signatures)}
        try:
            coll = await self._coll()
            cursor = coll.find(query, {"_id": 0}).sort([("doc_id", 1), ("index", 1)]).limit(limit)
            return [d async for d in cursor]
        except Exception as exc:  # noqa: BLE001 - table questions then fall back to the passage routes
            logger.warning("Table store unavailable: %s", exc)
            return []
