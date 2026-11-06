"""
MongoDB store for per-turn pipeline traces (collection `rag_traces`).

Traces expire through a TTL index (RAG_TRACE_RETENTION_DAYS). Without a reachable MongoDB the
store keeps the most recent traces in memory so diagnosis still works on a single instance.
"""

from __future__ import annotations

import logging
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from motor.motor_asyncio import AsyncIOMotorClient

from ...domain.entities import normalize_tenant_id
from ...domain.ports import TraceStorePort

logger = logging.getLogger("aip-rag.repo.mongo_trace")

MEMORY_CAPACITY = 500


def _feedback_matches(record: Dict[str, Any], feedback: Optional[str]) -> bool:
    if not feedback:
        return True
    rating = (record.get("feedback") or {}).get("polarity")
    return rating is not None if feedback == "any" else rating == feedback


class MongoTraceStore(TraceStorePort):
    def __init__(self, mongo_uri: str = "", retention_days: int = 14) -> None:
        self.mongo_uri = mongo_uri
        self.retention_days = retention_days
        self._client: Optional[AsyncIOMotorClient] = None
        self._indexes_ensured = False
        self._memory: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()

    def _collection(self) -> Any:
        if self._client is None:
            self._client = AsyncIOMotorClient(self.mongo_uri, serverSelectionTimeoutMS=2000)
        db_name = self.mongo_uri.split("/")[-1].split("?")[0] or "ai_platform"
        return self._client[db_name]["rag_traces"]

    async def _ensure_indexes(self, coll: Any) -> None:
        if self._indexes_ensured:
            return
        await coll.create_index([("trace_id", 1)], unique=True)
        await coll.create_index([("tenant_id", 1), ("created_at", -1)])
        await coll.create_index([("tenant_id", 1), ("session_id", 1), ("created_at", -1)])
        await coll.create_index([("tenant_id", 1), ("feedback.polarity", 1), ("created_at", -1)])
        if self.retention_days > 0:
            await coll.create_index("expires_from", expireAfterSeconds=self.retention_days * 86400)
        self._indexes_ensured = True

    def _remember(self, record: Dict[str, Any]) -> None:
        self._memory[record["trace_id"]] = record
        self._memory.move_to_end(record["trace_id"])
        while len(self._memory) > MEMORY_CAPACITY:
            self._memory.popitem(last=False)

    async def save(self, record: Dict[str, Any]) -> None:
        record = dict(record)
        record["tenant_id"] = normalize_tenant_id(record.get("tenant_id"))
        if not self.mongo_uri:
            self._remember(record)
            return
        doc = dict(record, expires_from=datetime.fromtimestamp(record.get("created_at") or 0, tz=timezone.utc))
        try:
            coll = self._collection()
            await self._ensure_indexes(coll)
            await coll.replace_one({"trace_id": record["trace_id"]}, doc, upsert=True)
        except Exception as exc:  # noqa: BLE001 - tracing never fails a chat turn
            logger.warning("Trace %s kept in memory (MongoDB unavailable: %s)", record.get("trace_id"), exc)
            self._remember(record)

    async def get(self, trace_id: str, tenant_id: str) -> Optional[Dict[str, Any]]:
        tenant_id = normalize_tenant_id(tenant_id)
        mem = self._memory.get(trace_id)
        if mem is not None:
            return mem if mem.get("tenant_id") == tenant_id else None
        if not self.mongo_uri:
            return None
        try:
            doc = await self._collection().find_one({"trace_id": trace_id, "tenant_id": tenant_id}, {"_id": 0, "expires_from": 0})
        except Exception as exc:  # noqa: BLE001
            logger.warning("Trace lookup failed for %s: %s", trace_id, exc)
            return None
        return doc

    async def list(
        self,
        tenant_id: str,
        session_id: Optional[str] = None,
        feedback: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        tenant_id = normalize_tenant_id(tenant_id)
        mem = [
            r for r in reversed(self._memory.values())
            if r.get("tenant_id") == tenant_id and (not session_id or r.get("session_id") == session_id)
            and _feedback_matches(r, feedback)
        ]
        if not self.mongo_uri:
            return mem[:limit]
        query: Dict[str, Any] = {"tenant_id": tenant_id}
        if session_id:
            query["session_id"] = session_id
        if feedback == "any":
            query["feedback.polarity"] = {"$exists": True}
        elif feedback:
            query["feedback.polarity"] = feedback
        try:
            cursor = self._collection().find(query, {"_id": 0, "expires_from": 0}).sort("created_at", -1).limit(limit)
            docs = [d async for d in cursor]
        except Exception as exc:  # noqa: BLE001
            logger.warning("Trace listing failed: %s", exc)
            return mem[:limit]
        seen = {d["trace_id"] for d in docs}
        return (docs + [r for r in mem if r["trace_id"] not in seen])[:limit]

    async def attach_feedback(self, trace_id: str, tenant_id: str, feedback: Dict[str, Any]) -> bool:
        tenant_id = normalize_tenant_id(tenant_id)
        mem = self._memory.get(trace_id)
        if mem is not None and mem.get("tenant_id") == tenant_id:
            mem["feedback"] = feedback
            return True
        if not self.mongo_uri:
            return False
        try:
            res = await self._collection().update_one(
                {"trace_id": trace_id, "tenant_id": tenant_id}, {"$set": {"feedback": feedback}}
            )
            return bool(res.matched_count)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Attaching feedback to trace %s failed: %s", trace_id, exc)
            return False
