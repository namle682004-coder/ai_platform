from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime, timezone

from common.security.argon2_hasher import generate_api_key
from common.interfaces.base import IKeyRepository
from common.repositories.mongo_repositories import key_repository

router = APIRouter(prefix="/admin/v1", tags=["Admin - API Keys & Quota Control"])


def get_key_repo() -> IKeyRepository:
    return key_repository


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


@router.post("/keys", summary="Create New API Key in MongoDB Atlas")
async def create_api_key(
    request: CreateAPIKeyRequest,
    repo: IKeyRepository = Depends(get_key_repo)
):
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

    created = await repo.create_key(record)

    return {
        "key_id": created["key_id"],
        "tenant_id": request.tenant_id,
        "api_key_plaintext": raw_key,
        "rpm_limit": request.rpm_limit,
        "tpm_limit": request.tpm_limit,
        "concurrency_limit": request.concurrency_limit,
        "message": "API key created and persisted in MongoDB Atlas successfully.",
    }


@router.get("/keys", summary="List All API Keys and Quotas from MongoDB Atlas")
async def list_api_keys(repo: IKeyRepository = Depends(get_key_repo)):
    keys = await repo.list_keys()
    return {"object": "list", "data": keys}


@router.put("/keys/{key_id}/quota", summary="Adjust Quota Limits in MongoDB Atlas")
async def update_api_key_quota(
    key_id: str,
    request: UpdateQuotaRequest,
    repo: IKeyRepository = Depends(get_key_repo)
):
    updates = {}
    if request.rpm_limit is not None:
        updates["rpm_limit"] = request.rpm_limit
    if request.tpm_limit is not None:
        updates["tpm_limit"] = request.tpm_limit
    if request.concurrency_limit is not None:
        updates["concurrency_limit"] = request.concurrency_limit

    updated = await repo.update_quota(key_id, updates)
    if not updated:
        raise HTTPException(status_code=404, detail=f"API key ID '{key_id}' not found.")

    return {
        "message": f"Quota updated in MongoDB Atlas for key '{key_id}'.",
        "key_id": key_id,
        "updated_quota": updates,
        "data": updated
    }


@router.delete("/keys/{key_id}", summary="Delete API Key from MongoDB Atlas")
async def revoke_api_key(key_id: str, repo: IKeyRepository = Depends(get_key_repo)):
    deleted = await repo.delete_key(key_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"API key ID '{key_id}' not found.")

    return {"message": f"API key '{key_id}' deleted from MongoDB Atlas."}
