from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from common.interfaces.keys import IKeyRepository, IAliasRepository
from common.database.mongodb import mongo_manager
from common.security.argon2_hasher import generate_api_key

DEFAULT_KEYS = [
    {
        "key_id": "key_retail_bank_prod",
        "tenant_id": "TENANT_RETAIL_BANK",
        "prefix": "aip_live_bank...",
        "hashed_key": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        "cost_center": "CC_DIGITAL_BANKING",
        "allowed_aliases": ["*"],
        "rpm_limit": 120,
        "tpm_limit": 500000,
        "concurrency_limit": 10,
        "status": "enabled",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
]

DEFAULT_ALIASES = [
    {
        "alias_name": "chat-general-standard",
        "target_model": "deepseek-v3",
        "provider": "vllm_local",
        "status": "active",
        "description": "Standard PhoGPT/DeepSeek V3 Chat Completion model",
    },
    {
        "alias_name": "stt-whisper-v3",
        "target_model": "phowhisper-large-v3",
        "provider": "triton_local",
        "status": "active",
        "description": "Real-time Automatic Speech Recognition (Vietnamese)",
    },
]


class MongoKeyRepository(IKeyRepository):
    """MongoDB Atlas implementation for API Keys and Quota Management."""

    def __init__(self):
        self._keys_cache: Dict[str, Dict[str, Any]] = {
            k["key_id"]: dict(k) for k in DEFAULT_KEYS
        }
        self._key_requests_cache: Dict[str, Dict[str, Any]] = {}

    async def create_key(self, record: Dict[str, Any]) -> Dict[str, Any]:
        db = mongo_manager.get_database()
        if db is not None:
            try:
                await db.api_keys.insert_one(dict(record))
            except Exception:
                pass
        record.pop("_id", None)
        self._keys_cache[record["key_id"]] = record
        return record

    async def list_keys(self) -> List[Dict[str, Any]]:
        db = mongo_manager.get_database()
        if db is not None:
            try:
                cursor = db.api_keys.find({}, {"_id": 0, "hashed_key": 0})
                keys = await cursor.to_list(length=100)
                if keys:
                    for k in keys:
                        k.pop("_id", None)
                        self._keys_cache[k["key_id"]] = k
                    return keys
            except Exception:
                pass
        return [dict(k) for k in self._keys_cache.values()]

    async def update_quota(self, key_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if key_id in self._keys_cache:
            self._keys_cache[key_id].update(updates)
            db = mongo_manager.get_database()
            if db is not None:
                try:
                    await db.api_keys.update_one({"key_id": key_id}, {"$set": updates})
                except Exception:
                    pass
            return self._keys_cache[key_id]
        return None

    async def delete_key(self, key_id: str) -> bool:
        if key_id in self._keys_cache:
            del self._keys_cache[key_id]
            db = mongo_manager.get_database()
            if db is not None:
                try:
                    await db.api_keys.delete_one({"key_id": key_id})
                except Exception:
                    pass
            return True
        return False

    async def create_key_request(self, request_record: Dict[str, Any]) -> Dict[str, Any]:
        db = mongo_manager.get_database()
        if db is not None:
            try:
                await db.key_requests.insert_one(dict(request_record))
            except Exception:
                pass
        request_record.pop("_id", None)
        self._key_requests_cache[request_record["request_id"]] = request_record
        return request_record

    async def list_pending_key_requests(self) -> List[Dict[str, Any]]:
        db = mongo_manager.get_database()
        if db is not None:
            try:
                cursor = db.key_requests.find({"status": "pending_approval"}, {"_id": 0})
                reqs = await cursor.to_list(length=100)
                if reqs:
                    for r in reqs:
                        r.pop("_id", None)
                        self._key_requests_cache[r["request_id"]] = r
                    return reqs
            except Exception:
                pass
        return [r for r in self._key_requests_cache.values() if r.get("status") == "pending_approval"]

    async def approve_key_request(self, request_id: str) -> Optional[Dict[str, Any]]:
        req = self._key_requests_cache.get(request_id)
        db = mongo_manager.get_database()
        if db is not None and not req:
            try:
                req = await db.key_requests.find_one({"request_id": request_id}, {"_id": 0})
            except Exception:
                pass

        if not req:
            return None

        raw_key, hashed_key = generate_api_key(prefix="aip_live_")
        key_id = f"key_{raw_key[-10:]}"
        now = datetime.now(timezone.utc).isoformat()

        key_record = {
            "key_id": key_id,
            "tenant_id": req["tenant_id"],
            "prefix": raw_key[:12] + "...",
            "hashed_key": hashed_key,
            "rpm_limit": req.get("rpm_limit", 60),
            "tpm_limit": req.get("tpm_limit", 100000),
            "concurrency_limit": req.get("concurrency_limit", 5),
            "status": "enabled",
            "created_at": now,
        }

        await self.create_key(key_record)

        req["status"] = "approved"
        req["approved_key_id"] = key_id
        req["api_key_plaintext"] = raw_key
        req["updated_at"] = now

        if db is not None:
            try:
                await db.key_requests.update_one({"request_id": request_id}, {"$set": req})
            except Exception:
                pass

        req.pop("_id", None)
        return req

    async def reject_key_request(self, request_id: str, reason: str) -> Optional[Dict[str, Any]]:
        req = self._key_requests_cache.get(request_id)
        db = mongo_manager.get_database()
        if db is not None and not req:
            try:
                req = await db.key_requests.find_one({"request_id": request_id}, {"_id": 0})
            except Exception:
                pass

        if not req:
            return None

        now = datetime.now(timezone.utc).isoformat()
        req["status"] = "rejected"
        req["rejection_reason"] = reason
        req["updated_at"] = now

        if db is not None:
            try:
                await db.key_requests.update_one({"request_id": request_id}, {"$set": req})
            except Exception:
                pass

        req.pop("_id", None)
        return req


class MongoAliasRepository(IAliasRepository):
    """MongoDB Atlas implementation for Model Aliases Registry."""

    def __init__(self):
        self._aliases_cache: Dict[str, Dict[str, Any]] = {
            a["alias_name"]: dict(a) for a in DEFAULT_ALIASES
        }

    async def list_aliases(self) -> Dict[str, Any]:
        db = mongo_manager.get_database()
        if db is not None:
            try:
                cursor = db.aliases.find({}, {"_id": 0})
                aliases = await cursor.to_list(length=100)
                if aliases:
                    for a in aliases:
                        a.pop("_id", None)
                        self._aliases_cache[a["alias_name"]] = a
                    return self._aliases_cache
            except Exception:
                pass
        return self._aliases_cache

    async def update_alias_status(self, alias_name: str, status: str) -> Optional[Dict[str, Any]]:
        if alias_name in self._aliases_cache:
            self._aliases_cache[alias_name]["status"] = status
            db = mongo_manager.get_database()
            if db is not None:
                try:
                    await db.aliases.update_one({"alias_name": alias_name}, {"$set": {"status": status}})
                except Exception:
                    pass
            return self._aliases_cache[alias_name]
        return None


key_repository = MongoKeyRepository()
alias_repository = MongoAliasRepository()
