"""
MongoDB and In-Memory repository for tenant support configuration (Requirement #17).
"""

from __future__ import annotations

import time
from typing import Any, Dict, Optional

from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import ReturnDocument

from ...config import rag_settings
from ...domain.support_config import SupportRepositoryPort


def _strip(doc: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if doc:
        doc.pop("_id", None)
    return doc


class InMemorySupportRepository(SupportRepositoryPort):
    def __init__(self) -> None:
        self._configs: Dict[str, Dict[str, Any]] = {}

    async def get_support_config(self, tenant_id: str) -> Optional[Dict[str, Any]]:
        norm = (tenant_id or "default").strip()
        cfg = self._configs.get(norm)
        return dict(cfg) if cfg else None

    async def save_support_config(
        self, tenant_id: str, hotline: str, support_method: str, instructions: str
    ) -> Dict[str, Any]:
        norm = (tenant_id or "default").strip()
        record = {
            "tenant_id": norm,
            "hotline": (hotline or "").strip(),
            "support_method": (support_method or "").strip(),
            "instructions": (instructions or "").strip(),
            "updated_at": int(time.time()),
        }
        self._configs[norm] = record
        return dict(record)


class MongoSupportRepository(SupportRepositoryPort):
    def __init__(self, mongo_uri: Optional[str] = None) -> None:
        self.mongo_uri = mongo_uri or rag_settings.mongo_uri
        self._client: Optional[AsyncIOMotorClient] = None
        self._indexed = False

    async def _db(self):
        if self._client is None:
            self._client = AsyncIOMotorClient(self.mongo_uri)
        db_name = self.mongo_uri.split("/")[-1].split("?")[0] or "ai_platform"
        db = self._client[db_name]
        if not self._indexed:
            try:
                await db.rag_support_configs.create_index("tenant_id", unique=True)
                self._indexed = True
            except Exception:
                pass
        return db

    async def get_support_config(self, tenant_id: str) -> Optional[Dict[str, Any]]:
        norm = (tenant_id or "default").strip()
        try:
            db = await self._db()
            doc = await db.rag_support_configs.find_one({"tenant_id": norm})
            return _strip(doc)
        except Exception:
            return None

    async def save_support_config(
        self, tenant_id: str, hotline: str, support_method: str, instructions: str
    ) -> Dict[str, Any]:
        norm = (tenant_id or "default").strip()
        record = {
            "tenant_id": norm,
            "hotline": (hotline or "").strip(),
            "support_method": (support_method or "").strip(),
            "instructions": (instructions or "").strip(),
            "updated_at": int(time.time()),
        }
        try:
            db = await self._db()
            doc = await db.rag_support_configs.find_one_and_update(
                {"tenant_id": norm},
                {"$set": record},
                upsert=True,
                return_document=ReturnDocument.AFTER,
            )
            return _strip(doc) or record
        except Exception:
            return record
