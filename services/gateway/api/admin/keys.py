from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional
from common.security.argon2_hasher import generate_api_key

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


_API_KEYS_STORE: dict[str, dict] = {
    "key_01HXDEFAULT": {
        "key_id": "key_01HXDEFAULT",
        "tenant_id": "TENANT_DEFAULT",
        "prefix": "aip_live_",
        "rpm_limit": 60,
        "tpm_limit": 100000,
        "concurrency_limit": 5,
        "status": "enabled",
    }
}


@router.post("/keys", summary="Create New API Key with Initial Quota")
async def create_api_key(request: CreateAPIKeyRequest):
    raw_key, hashed_key = generate_api_key(prefix="aip_live_")
    key_id = f"key_{raw_key[-10:]}"

    record = {
        "key_id": key_id,
        "tenant_id": request.tenant_id,
        "prefix": raw_key[:12] + "...",
        "hashed_key": hashed_key,
        "rpm_limit": request.rpm_limit,
        "tpm_limit": request.tpm_limit,
        "concurrency_limit": request.concurrency_limit,
        "status": "enabled",
    }
    _API_KEYS_STORE[key_id] = record

    return {
        "key_id": key_id,
        "tenant_id": request.tenant_id,
        "api_key_plaintext": raw_key,
        "rpm_limit": request.rpm_limit,
        "tpm_limit": request.tpm_limit,
        "concurrency_limit": request.concurrency_limit,
        "message": "API key created successfully. Save plaintext key now; it will not be shown again.",
    }


@router.get("/keys", summary="List All API Keys and Assigned Quotas")
async def list_api_keys():
    return {"object": "list", "data": list(_API_KEYS_STORE.values())}


@router.put("/keys/{key_id}/quota", summary="Adjust & Update Quota Limits for API Key / Tenant")
async def update_api_key_quota(key_id: str, request: UpdateQuotaRequest):
    if key_id not in _API_KEYS_STORE:
        raise HTTPException(status_code=404, detail=f"API key ID '{key_id}' not found.")

    key_record = _API_KEYS_STORE[key_id]
    if request.rpm_limit is not None:
        key_record["rpm_limit"] = request.rpm_limit
    if request.tpm_limit is not None:
        key_record["tpm_limit"] = request.tpm_limit
    if request.concurrency_limit is not None:
        key_record["concurrency_limit"] = request.concurrency_limit

    return {
        "message": f"Quota limits updated successfully for key '{key_id}'.",
        "key_id": key_id,
        "tenant_id": key_record["tenant_id"],
        "updated_quota": {
            "rpm_limit": key_record["rpm_limit"],
            "tpm_limit": key_record["tpm_record"] if "tpm_record" in key_record else key_record["tpm_limit"],
            "concurrency_limit": key_record["concurrency_limit"],
        }
    }


@router.delete("/keys/{key_id}", summary="Revoke & Delete API Key")
async def revoke_api_key(key_id: str):
    if key_id not in _API_KEYS_STORE:
        raise HTTPException(status_code=404, detail=f"API key ID '{key_id}' not found.")

    del _API_KEYS_STORE[key_id]
    return {"message": f"API key '{key_id}' has been revoked and deleted."}
