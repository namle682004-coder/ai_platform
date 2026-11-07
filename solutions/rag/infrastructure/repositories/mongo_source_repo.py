"""
Source configurations (`rag_sources`), records read from structured sources (`rag_source_items`) and sync runs
(`rag_source_runs`). The sync lease is taken with an atomic find-and-update, so two workers never sync the same
source at once. `InMemorySourceRepository` has the same behaviour without MongoDB (tests, null adapter).
"""

from __future__ import annotations

import copy
import time
from typing import Any, Dict, List, Optional

from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import ReturnDocument

from ...config import rag_settings
from ...domain.sources import SourceItem, SourceRepositoryPort

RUNS_KEPT = 50


def _strip(doc: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if doc:
        doc.pop("_id", None)
    return doc


class MongoSourceRepository(SourceRepositoryPort):
    def __init__(self, mongo_uri: Optional[str] = None) -> None:
        self.mongo_uri = mongo_uri or rag_settings.mongo_uri
        self._client: Optional[AsyncIOMotorClient] = None
        self._indexed = False

    async def _db(self):
        if self._client is None:
            self._client = AsyncIOMotorClient(self.mongo_uri)
        db = self._client[self.mongo_uri.split("/")[-1].split("?")[0] or "ai_platform"]
        if not self._indexed:
            await db.rag_sources.create_index("source_id", unique=True)
            await db.rag_sources.create_index([("enabled", 1), ("next_sync_at", 1)])
            await db.rag_source_items.create_index([("source_id", 1), ("key", 1)], unique=True)
            await db.rag_source_items.create_index([("source_id", 1), ("partition", 1)])
            await db.rag_source_runs.create_index([("source_id", 1), ("started_at", -1)])
            self._indexed = True
        return db

    async def create(self, source: Dict[str, Any]) -> Dict[str, Any]:
        db = await self._db()
        await db.rag_sources.insert_one(dict(source))
        return source

    async def get(self, source_id: str, tenant_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        q: Dict[str, Any] = {"source_id": source_id}
        if tenant_id is not None:
            q["tenant_id"] = tenant_id
        return _strip(await (await self._db()).rag_sources.find_one(q))

    async def list(self, tenant_id: str) -> List[Dict[str, Any]]:
        cur = (await self._db()).rag_sources.find({"tenant_id": tenant_id}).sort("created_at", 1)
        return [_strip(d) async for d in cur]

    async def update(self, source_id: str, tenant_id: str, fields: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        doc = await (await self._db()).rag_sources.find_one_and_update(
            {"source_id": source_id, "tenant_id": tenant_id}, {"$set": fields}, return_document=ReturnDocument.AFTER)
        return _strip(doc)

    async def delete(self, source_id: str, tenant_id: str) -> bool:
        db = await self._db()
        res = await db.rag_sources.delete_one({"source_id": source_id, "tenant_id": tenant_id})
        if res.deleted_count:
            await db.rag_source_items.delete_many({"source_id": source_id})
            await db.rag_source_runs.delete_many({"source_id": source_id})
        return bool(res.deleted_count)

    async def due(self, now: float, limit: int = 20) -> List[Dict[str, Any]]:
        cur = (await self._db()).rag_sources.find({"enabled": True, "next_sync_at": {"$lte": now}}).limit(limit)
        return [_strip(d) async for d in cur]

    async def acquire(self, source_id: str, owner: str, now: float, ttl: float) -> bool:
        doc = await (await self._db()).rag_sources.find_one_and_update(
            {"source_id": source_id, "$or": [{"lease_until": {"$exists": False}}, {"lease_until": {"$lt": now}}]},
            {"$set": {"lease_owner": owner, "lease_until": now + ttl}})
        return doc is not None

    async def release(self, source_id: str, owner: str, fields: Dict[str, Any]) -> None:
        await (await self._db()).rag_sources.update_one(
            {"source_id": source_id, "lease_owner": owner},
            {"$set": fields, "$unset": {"lease_owner": "", "lease_until": ""}})

    async def upsert_records(self, source_id: str, items: List[SourceItem], hashes: Dict[str, str]) -> Dict[str, str]:
        db = await self._db()
        changed: Dict[str, str] = {}
        existing = {d["key"]: d async for d in db.rag_source_items.find(
            {"source_id": source_id, "key": {"$in": [i.key for i in items]}}, {"key": 1, "hash": 1, "partition": 1})}
        now = time.time()
        for it in items:
            old = existing.get(it.key)
            if old and old.get("hash") == hashes[it.key] and old.get("partition") == it.partition:
                continue
            if old and old.get("partition") != it.partition:
                changed[f"{it.key}\x00old"] = old.get("partition", "")  # the record left its old partition
            await db.rag_source_items.update_one(
                {"source_id": source_id, "key": it.key},
                {"$set": {"partition": it.partition, "data": it.data, "title": it.title, "hash": hashes[it.key],
                          "updated_at": now}}, upsert=True)
            changed[it.key] = it.partition
        return changed

    async def remove_records_except(self, source_id: str, keep: List[str]) -> Dict[str, str]:
        db = await self._db()
        gone = {d["key"]: d.get("partition", "") async for d in db.rag_source_items.find(
            {"source_id": source_id, "key": {"$nin": keep}}, {"key": 1, "partition": 1})}
        if gone:
            await db.rag_source_items.delete_many({"source_id": source_id, "key": {"$in": list(gone)}})
        return gone

    async def records_of(self, source_id: str, partition: str) -> List[Dict[str, Any]]:
        cur = (await self._db()).rag_source_items.find({"source_id": source_id, "partition": partition}).sort("key", 1)
        return [_strip(d) async for d in cur]

    async def add_run(self, run: Dict[str, Any]) -> None:
        db = await self._db()
        await db.rag_source_runs.insert_one(dict(run))
        old = [d["_id"] async for d in db.rag_source_runs.find({"source_id": run["source_id"]}, {"_id": 1})
               .sort("started_at", -1).skip(RUNS_KEPT)]
        if old:
            await db.rag_source_runs.delete_many({"_id": {"$in": old}})

    async def runs(self, source_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        cur = (await self._db()).rag_source_runs.find({"source_id": source_id}).sort("started_at", -1).limit(limit)
        return [_strip(d) async for d in cur]


class InMemorySourceRepository(SourceRepositoryPort):
    def __init__(self) -> None:
        self.sources: Dict[str, Dict[str, Any]] = {}
        self.items: Dict[str, Dict[str, Dict[str, Any]]] = {}
        self._runs: List[Dict[str, Any]] = []

    async def create(self, source):
        self.sources[source["source_id"]] = copy.deepcopy(source)
        return source

    async def get(self, source_id, tenant_id=None):
        s = self.sources.get(source_id)
        return copy.deepcopy(s) if s and (tenant_id is None or s["tenant_id"] == tenant_id) else None

    async def list(self, tenant_id):
        return [copy.deepcopy(s) for s in self.sources.values() if s["tenant_id"] == tenant_id]

    async def update(self, source_id, tenant_id, fields):
        s = self.sources.get(source_id)
        if not s or s["tenant_id"] != tenant_id:
            return None
        s.update(copy.deepcopy(fields))
        return copy.deepcopy(s)

    async def delete(self, source_id, tenant_id):
        s = self.sources.get(source_id)
        if not s or s["tenant_id"] != tenant_id:
            return False
        del self.sources[source_id]
        self.items.pop(source_id, None)
        return True

    async def due(self, now, limit=20):
        return [copy.deepcopy(s) for s in self.sources.values()
                if s.get("enabled") and s.get("next_sync_at", 0) <= now][:limit]

    async def acquire(self, source_id, owner, now, ttl):
        s = self.sources.get(source_id)
        if not s or s.get("lease_until", 0) >= now:
            return False
        s["lease_owner"], s["lease_until"] = owner, now + ttl
        return True

    async def release(self, source_id, owner, fields):
        s = self.sources.get(source_id)
        if s and s.get("lease_owner") == owner:
            s.update(copy.deepcopy(fields))
            s.pop("lease_owner", None)
            s.pop("lease_until", None)

    async def upsert_records(self, source_id, items, hashes):
        store = self.items.setdefault(source_id, {})
        changed = {}
        for it in items:
            old = store.get(it.key)
            if old and old["hash"] == hashes[it.key] and old["partition"] == it.partition:
                continue
            if old and old["partition"] != it.partition:
                changed[f"{it.key}\x00old"] = old["partition"]
            store[it.key] = {"key": it.key, "partition": it.partition, "data": copy.deepcopy(it.data),
                             "title": it.title, "hash": hashes[it.key]}
            changed[it.key] = it.partition
        return changed

    async def remove_records_except(self, source_id, keep):
        store = self.items.setdefault(source_id, {})
        gone = {k: v["partition"] for k, v in store.items() if k not in set(keep)}
        for k in gone:
            del store[k]
        return gone

    async def records_of(self, source_id, partition):
        return [copy.deepcopy(v) for k, v in sorted(self.items.get(source_id, {}).items()) if v["partition"] == partition]

    async def add_run(self, run):
        self._runs.append(copy.deepcopy(run))

    async def runs(self, source_id, limit=20):
        return [r for r in reversed(self._runs) if r["source_id"] == source_id][:limit]
