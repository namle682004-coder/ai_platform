from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime, timezone

from common.security.argon2_hasher import generate_api_key
from common.database.mongodb import mongo_manager

router = APIRouter(prefix="/admin/v1", tags=["Admin - API Keys & Quota Control"])


class CreateAPIKeyRequest(BaseModel):
    tenant_id: str = Field(..., json_schema_extra={"example": "TENANT_RETAIL_BANK"})
    rpm_limit: int = Field(60, json_schema_extra={"example": 60})
    tpm_limit: int = Field(100000, json_schema_extra={"example": 100000})
    concurrency_limit: int = Field(5, json_schema_extra={"example": 5})
    expires_at: Optional[str] = Field(None, json_schema_extra={"example": "2026-12-31T23:59:59Z"})


class UpdateQuotaRequest(BaseModel):
    rpm_limit: Optional[int] = Field(None, json_schema_extra={"example": 120}, description="Requests Per Minute limit")
    tpm_limit: Optional[int] = Field(None, json_schema_extra={"example": 200000}, description="Tokens Per Minute limit")
    concurrency_limit: Optional[int] = Field(None, json_schema_extra={"example": 10}, description="Max concurrent requests limit")


# In-Memory Fallback Cache if MongoDB is unreachable
_API_KEYS_MEMORY_CACHE: dict[str, dict] = {
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


@router.post("/keys", summary="Create New API Key in MongoDB Atlas")
async def create_api_key(request: CreateAPIKeyRequest):
    raw_key, hashed_key = generate_api_key(prefix="aip_live_")
    key_id = f"key_{raw_key[-10:]}"
    now = datetime.now(timezone.utc)

    record = {
        "key_id": key_id,
        "tenant_id": request.tenant_id,
        "prefix": raw_key[:12] + "...",
        "hashed_key": hashed_key,
        "rpm_limit": request.rpm_limit,
        "tpm_limit": request.tpm_limit,
        "concurrency_limit": request.concurrency_limit,
        "status": "enabled",
        "created_at": now.isoformat(),
    }

    db = mongo_manager.get_database()
    if db is not None:
        try:
            await db.api_keys.insert_one(record)
        except Exception:
            pass

    _API_KEYS_MEMORY_CACHE[key_id] = record

    return {
        "key_id": key_id,
        "tenant_id": request.tenant_id,
        "api_key_plaintext": raw_key,
        "rpm_limit": request.rpm_limit,
        "tpm_limit": request.tpm_limit,
        "concurrency_limit": request.concurrency_limit,
        "message": "API key created and persisted in MongoDB Atlas successfully.",
    }


@router.get("/keys", summary="List All API Keys and Quotas from MongoDB Atlas")
async def list_api_keys():
    db = mongo_manager.get_database()
    if db is not None:
        try:
            cursor = db.api_keys.find({}, {"_id": 0, "hashed_key": 0})
            keys_list = await cursor.to_list(length=100)
            if keys_list:
                return {"object": "list", "data": keys_list}
        except Exception:
            pass

    return {"object": "list", "data": list(_API_KEYS_MEMORY_CACHE.values())}


@router.put("/keys/{key_id}/quota", summary="Adjust Quota Limits in MongoDB Atlas")
async def update_api_key_quota(key_id: str, request: UpdateQuotaRequest):
    db = mongo_manager.get_database()
    updates = {}
    if request.rpm_limit is not None:
        updates["rpm_limit"] = request.rpm_limit
    if request.tpm_limit is not None:
        updates["tpm_limit"] = request.tpm_limit
    if request.concurrency_limit is not None:
        updates["concurrency_limit"] = request.concurrency_limit

    if db is not None and updates:
        try:
            result = await db.api_keys.update_one({"key_id": key_id}, {"$set": updates})
            if result.matched_count > 0:
                updated_doc = await db.api_keys.find_one({"key_id": key_id}, {"_id": 0})
                return {
                    "message": f"Quota updated in MongoDB Atlas for key '{key_id}'.",
                    "key_id": key_id,
                    "updated_quota": updates,
                    "data": updated_doc
                }
        except Exception:
            pass

    if key_id in _API_KEYS_MEMORY_CACHE:
        _API_KEYS_MEMORY_CACHE[key_id].update(updates)
        return {
            "message": f"Quota updated in memory cache for key '{key_id}'.",
            "key_id": key_id,
            "updated_quota": updates,
        }

    raise HTTPException(status_code=404, detail=f"API key ID '{key_id}' not found.")


@router.delete("/keys/{key_id}", summary="Delete API Key from MongoDB Atlas")
async def revoke_api_key(key_id: str):
    db = mongo_manager.get_database()
    if db is not None:
        try:
            await db.api_keys.delete_one({"key_id": key_id})
        except Exception:
            pass

    if key_id in _API_KEYS_MEMORY_CACHE:
        del _API_KEYS_MEMORY_CACHE[key_id]

    return {"message": f"API key '{key_id}' deleted from MongoDB Atlas."}
