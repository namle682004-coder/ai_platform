from typing import Optional, Dict, Any, List
from common.interfaces.base import IKeyRepository, IAliasRepository, IEndpointRepository, IJobRepository
from common.database.mongodb import mongo_manager
from common.security.argon2_hasher import generate_api_key
from datetime import datetime, timezone

DEFAULT_ALIASES_LIST = [
    {"alias_name": "chat-general-standard", "model_name": "Qwen3-8B", "runtime": "vllm", "min_vram_gb": 24, "status": "enabled"},
    {"alias_name": "chat-general-high-quality", "model_name": "Qwen3-14B", "runtime": "vllm", "min_vram_gb": 32, "status": "enabled"},
    {"alias_name": "embed-standard", "model_name": "Qwen3-Embedding-8B", "runtime": "vllm", "min_vram_gb": 24, "status": "enabled"},
    {"alias_name": "embed-cost-optimized", "model_name": "bge-m3", "runtime": "triton", "min_vram_gb": 8, "status": "enabled"},
    {"alias_name": "translate-vi-standard", "model_name": "NLLB-200 3.3B", "runtime": "ctranslate2", "min_vram_gb": 16, "status": "enabled"},
    {"alias_name": "stt-vn-standard", "model_name": "PhoWhisper", "runtime": "faster-whisper", "min_vram_gb": 16, "status": "enabled"},
    {"alias_name": "tts-vi-standard", "model_name": "viXTTS", "runtime": "tts-adapter", "min_vram_gb": 16, "status": "enabled"},
    {"alias_name": "idp-standard", "model_name": "PaddleOCR-VL", "runtime": "ocr-server", "min_vram_gb": 16, "status": "enabled"},
    {"alias_name": "image-gen-standard", "model_name": "FLUX.1-schnell", "runtime": "image-worker", "min_vram_gb": 24, "status": "enabled"},
    {"alias_name": "video-gen-standard", "model_name": "Wan2.2 T2V-A14B", "runtime": "video-worker", "min_vram_gb": 80, "status": "enabled"},
    {"alias_name": "moderation-multimodal", "model_name": "Llama Guard 4", "runtime": "moderation-server", "min_vram_gb": 24, "status": "enabled"},
]

DEFAULT_ENDPOINTS_LIST = [
    {"endpoint_id": "chat_completions", "path": "/v1/chat/completions", "method": "POST", "status": "enabled", "description": "LLM Chat Completions API"},
    {"endpoint_id": "text_completions", "path": "/v1/completions", "method": "POST", "status": "enabled", "description": "Text Completion API"},
    {"endpoint_id": "embeddings", "path": "/v1/embeddings", "method": "POST", "status": "enabled", "description": "Vector Embeddings API"},
    {"endpoint_id": "audio_transcriptions", "path": "/v1/audio/transcriptions", "method": "POST", "status": "enabled", "description": "Speech-to-Text API"},
    {"endpoint_id": "audio_speech", "path": "/v1/audio/speech", "method": "POST", "status": "enabled", "description": "Text-to-Speech API"},
    {"endpoint_id": "images_generations", "path": "/v1/images/generations", "method": "POST", "status": "enabled", "description": "Image Generation API"},
    {"endpoint_id": "moderations", "path": "/v1/moderations", "method": "POST", "status": "enabled", "description": "Content Moderation API"},
    {"endpoint_id": "predictions", "path": "/v1/predictions", "method": "POST", "status": "enabled", "description": "Custom Predictions API"},
    {"endpoint_id": "async_jobs", "path": "/v1/jobs", "method": "POST", "status": "enabled", "description": "Async Jobs Creation API"},
]

DEFAULT_KEY_RECORD = {
    "key_id": "key_01HXDEFAULT",
    "tenant_id": "TENANT_RETAIL_BANK",
    "prefix": "aip_live_test_...",
    "rpm_limit": 120,
    "tpm_limit": 200000,
    "concurrency_limit": 10,
    "status": "enabled",
}


class MongoKeyRepository(IKeyRepository):
    def __init__(self):
        self._keys_cache: Dict[str, Dict[str, Any]] = {
            DEFAULT_KEY_RECORD["key_id"]: dict(DEFAULT_KEY_RECORD)
        }
        self._key_requests_cache: Dict[str, Dict[str, Any]] = {}

    async def create_key(self, record: Dict[str, Any]) -> Dict[str, Any]:
        self._keys_cache[record["key_id"]] = record
        db = mongo_manager.get_database()
        if db is not None:
            try:
                await db.api_keys.insert_one(record)
            except Exception:
                pass
        return record

    async def list_keys(self) -> List[Dict[str, Any]]:
        db = mongo_manager.get_database()
        if db is not None:
            try:
                cursor = db.api_keys.find({}, {"_id": 0, "hashed_key": 0})
                keys = await cursor.to_list(length=100)
                if keys:
                    for k in keys:
                        self._keys_cache[k["key_id"]] = k
                    return keys
            except Exception:
                pass
        return list(self._keys_cache.values())

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

    async def create_key_request(self, request_record: Dict[str, Any]) -> Dict[str, Any]:
        self._key_requests_cache[request_record["request_id"]] = request_record
        db = mongo_manager.get_database()
        if db is not None:
            try:
                await db.key_requests.insert_one(request_record)
            except Exception:
                pass
        return request_record

    async def list_pending_key_requests(self) -> List[Dict[str, Any]]:
        db = mongo_manager.get_database()
        if db is not None:
            try:
                cursor = db.key_requests.find({"status": "pending_approval"}, {"_id": 0})
                reqs = await cursor.to_list(length=100)
                if reqs:
                    for r in reqs:
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

        # Generate API key
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

        # Save approved key
        await self.create_key(key_record)

        # Update request status to approved
        req["status"] = "approved"
        req["approved_key_id"] = key_id
        req["api_key_plaintext"] = raw_key
        req["updated_at"] = now

        if db is not None:
            try:
                await db.key_requests.update_one({"request_id": request_id}, {"$set": req})
            except Exception:
                pass

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

        return req


class MongoAliasRepository(IAliasRepository):
    def __init__(self):
        self._aliases_cache: Dict[str, Dict[str, Any]] = {
            item["alias_name"]: dict(item) for item in DEFAULT_ALIASES_LIST
        }

    async def list_aliases(self) -> Dict[str, Any]:
        db = mongo_manager.get_database()
        if db is not None:
            try:
                cursor = db.aliases.find({}, {"_id": 0})
                aliases = await cursor.to_list(length=100)
                if aliases:
                    for item in aliases:
                        self._aliases_cache[item["alias_name"]] = item
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


class MongoEndpointRepository(IEndpointRepository):
    def __init__(self):
        self._endpoints_cache: Dict[str, Dict[str, Any]] = {
            item["endpoint_id"]: dict(item) for item in DEFAULT_ENDPOINTS_LIST
        }

    async def list_endpoints(self) -> Dict[str, Any]:
        db = mongo_manager.get_database()
        if db is not None:
            try:
                cursor = db.endpoints.find({}, {"_id": 0})
                eps = await cursor.to_list(length=100)
                if eps:
                    for item in eps:
                        self._endpoints_cache[item["endpoint_id"]] = item
                    return self._endpoints_cache
            except Exception:
                pass
        return self._endpoints_cache

    async def update_endpoint_status(self, endpoint_id: str, status: str) -> Optional[Dict[str, Any]]:
        if endpoint_id in self._endpoints_cache:
            self._endpoints_cache[endpoint_id]["status"] = status
            db = mongo_manager.get_database()
            if db is not None:
                try:
                    await db.endpoints.update_one({"endpoint_id": endpoint_id}, {"$set": {"status": status}})
                except Exception:
                    pass
            return self._endpoints_cache[endpoint_id]
        return None


class MongoJobRepository(IJobRepository):
    def __init__(self):
        self._jobs_cache: Dict[str, Dict[str, Any]] = {}

    async def create_job(self, job_record: Dict[str, Any]) -> Dict[str, Any]:
        self._jobs_cache[job_record["job_id"]] = job_record
        db = mongo_manager.get_database()
        if db is not None:
            try:
                await db.jobs.insert_one(job_record)
            except Exception:
                pass
        return job_record

    async def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        if job_id in self._jobs_cache:
            return self._jobs_cache[job_id]
        db = mongo_manager.get_database()
        if db is not None:
            try:
                doc = await db.jobs.find_one({"job_id": job_id}, {"_id": 0})
                if doc:
                    self._jobs_cache[job_id] = doc
                    return doc
            except Exception:
                pass
        return None

    async def update_job_status(self, job_id: str, status: str, updates: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        payload = {"status": status}
        if updates:
            payload.update(updates)

        if job_id in self._jobs_cache:
            self._jobs_cache[job_id].update(payload)
            db = mongo_manager.get_database()
            if db is not None:
                try:
                    await db.jobs.update_one({"job_id": job_id}, {"$set": payload})
                except Exception:
                    pass
            return self._jobs_cache[job_id]
        return None


# Singletons
key_repository = MongoKeyRepository()
alias_repository = MongoAliasRepository()
endpoint_repository = MongoEndpointRepository()
job_repository = MongoJobRepository()
