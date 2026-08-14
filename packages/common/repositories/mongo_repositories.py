from typing import Optional, Dict, Any, List
from common.interfaces.base import IKeyRepository, IAliasRepository, IEndpointRepository, IJobRepository
from common.database.mongodb import mongo_manager


class MongoKeyRepository(IKeyRepository):
    def __init__(self):
        self._memory_cache: Dict[str, Dict[str, Any]] = {
            "key_01HXDEFAULT": {
                "key_id": "key_01HXDEFAULT",
                "tenant_id": "TENANT_RETAIL_BANK",
                "prefix": "aip_live_test_...",
                "rpm_limit": 120,
                "tpm_limit": 200000,
                "concurrency_limit": 10,
                "status": "enabled",
            }
        }

    async def create_key(self, record: Dict[str, Any]) -> Dict[str, Any]:
        db = mongo_manager.get_database()
        if db is not None:
            try:
                await db.api_keys.insert_one(record)
            except Exception:
                pass
        self._memory_cache[record["key_id"]] = record
        return record

    async def list_keys(self) -> List[Dict[str, Any]]:
        db = mongo_manager.get_database()
        if db is not None:
            try:
                cursor = db.api_keys.find({}, {"_id": 0, "hashed_key": 0})
                keys = await cursor.to_list(length=100)
                if keys:
                    return keys
            except Exception:
                pass
        return list(self._memory_cache.values())

    async def update_quota(self, key_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        db = mongo_manager.get_database()
        if db is not None and updates:
            try:
                res = await db.api_keys.update_one({"key_id": key_id}, {"$set": updates})
                if res.matched_count > 0:
                    return await db.api_keys.find_one({"key_id": key_id}, {"_id": 0})
            except Exception:
                pass

        if key_id in self._memory_cache:
            self._memory_cache[key_id].update(updates)
            return self._memory_cache[key_id]

        return None

    async def delete_key(self, key_id: str) -> bool:
        db = mongo_manager.get_database()
        if db is not None:
            try:
                await db.api_keys.delete_one({"key_id": key_id})
            except Exception:
                pass
        if key_id in self._memory_cache:
            del self._memory_cache[key_id]
            return True
        return True


class MongoAliasRepository(IAliasRepository):
    def __init__(self):
        self._memory_cache = {
            "chat-general-standard": {"model_name": "Qwen3-8B", "status": "enabled", "runtime": "vllm"},
            "chat-general-high-quality": {"model_name": "Qwen3-14B", "status": "enabled", "runtime": "vllm"},
            "embed-standard": {"model_name": "Qwen3-Embedding-8B", "status": "enabled", "runtime": "vllm"},
            "stt-vn-standard": {"model_name": "PhoWhisper", "status": "enabled", "runtime": "faster-whisper"},
            "tts-vi-standard": {"model_name": "viXTTS", "status": "enabled", "runtime": "tts-adapter"},
        }

    async def list_aliases(self) -> Dict[str, Any]:
        db = mongo_manager.get_database()
        if db is not None:
            try:
                cursor = db.aliases.find({}, {"_id": 0})
                aliases = await cursor.to_list(length=100)
                if aliases:
                    return {item["alias_name"]: item for item in aliases}
            except Exception:
                pass
        return self._memory_cache

    async def update_alias_status(self, alias_name: str, status: str) -> Optional[Dict[str, Any]]:
        db = mongo_manager.get_database()
        if db is not None:
            try:
                res = await db.aliases.update_one({"alias_name": alias_name}, {"$set": {"status": status}})
                if res.matched_count > 0:
                    return await db.aliases.find_one({"alias_name": alias_name}, {"_id": 0})
            except Exception:
                pass

        if alias_name in self._memory_cache:
            self._memory_cache[alias_name]["status"] = status
            return self._memory_cache[alias_name]
        return None


class MongoEndpointRepository(IEndpointRepository):
    def __init__(self):
        self._memory_cache = {
            "chat_completions": {"path": "/v1/chat/completions", "method": "POST", "status": "enabled", "description": "LLM Chat Completions API"},
            "text_completions": {"path": "/v1/completions", "method": "POST", "status": "enabled", "description": "Text Completion API"},
            "embeddings": {"path": "/v1/embeddings", "method": "POST", "status": "enabled", "description": "Vector Embeddings API"},
            "audio_transcriptions": {"path": "/v1/audio/transcriptions", "method": "POST", "status": "enabled", "description": "Speech-to-Text API"},
            "audio_speech": {"path": "/v1/audio/speech", "method": "POST", "status": "enabled", "description": "Text-to-Speech API"},
            "images_generations": {"path": "/v1/images/generations", "method": "POST", "status": "enabled", "description": "Image Generation API"},
            "moderations": {"path": "/v1/moderations", "method": "POST", "status": "enabled", "description": "Content Moderation API"},
            "predictions": {"path": "/v1/predictions", "method": "POST", "status": "enabled", "description": "Custom Predictions API"},
            "async_jobs": {"path": "/v1/jobs", "method": "POST", "status": "enabled", "description": "Async Jobs Creation API"},
        }

    async def list_endpoints(self) -> Dict[str, Any]:
        db = mongo_manager.get_database()
        if db is not None:
            try:
                cursor = db.endpoints.find({}, {"_id": 0})
                eps = await cursor.to_list(length=100)
                if eps:
                    return {item["endpoint_id"]: item for item in eps}
            except Exception:
                pass
        return self._memory_cache

    async def update_endpoint_status(self, endpoint_id: str, status: str) -> Optional[Dict[str, Any]]:
        db = mongo_manager.get_database()
        if db is not None:
            try:
                res = await db.endpoints.update_one({"endpoint_id": endpoint_id}, {"$set": {"status": status}})
                if res.matched_count > 0:
                    return await db.endpoints.find_one({"endpoint_id": endpoint_id}, {"_id": 0})
            except Exception:
                pass

        if endpoint_id in self._memory_cache:
            self._memory_cache[endpoint_id]["status"] = status
            return self._memory_cache[endpoint_id]
        return None


class MongoJobRepository(IJobRepository):
    def __init__(self):
        self._memory_cache: Dict[str, Dict[str, Any]] = {}

    async def create_job(self, job_record: Dict[str, Any]) -> Dict[str, Any]:
        db = mongo_manager.get_database()
        if db is not None:
            try:
                await db.jobs.insert_one(job_record)
            except Exception:
                pass
        self._memory_cache[job_record["job_id"]] = job_record
        return job_record

    async def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        db = mongo_manager.get_database()
        if db is not None:
            try:
                doc = await db.jobs.find_one({"job_id": job_id}, {"_id": 0})
                if doc:
                    return doc
            except Exception:
                pass
        return self._memory_cache.get(job_id)

    async def update_job_status(self, job_id: str, status: str, updates: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        payload = {"status": status}
        if updates:
            payload.update(updates)

        db = mongo_manager.get_database()
        if db is not None:
            try:
                res = await db.jobs.update_one({"job_id": job_id}, {"$set": payload})
                if res.matched_count > 0:
                    return await db.jobs.find_one({"job_id": job_id}, {"_id": 0})
            except Exception:
                pass

        if job_id in self._memory_cache:
            self._memory_cache[job_id].update(payload)
            return self._memory_cache[job_id]
        return None


# Singletons
key_repository = MongoKeyRepository()
alias_repository = MongoAliasRepository()
endpoint_repository = MongoEndpointRepository()
job_repository = MongoJobRepository()
