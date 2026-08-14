import uuid
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime, timezone

from common.security.argon2_hasher import generate_api_key
from common.interfaces.base import IKeyRepository
from common.repositories.mongo_repositories import key_repository

router = APIRouter(tags=["Admin & Staff - API Keys, Requests & Quota Control"])


def get_key_repo() -> IKeyRepository:
    return key_repository


class CreateAPIKeyRequest(BaseModel):
    tenant_id: str = Field(..., json_schema_extra={"example": "TENANT_RETAIL_BANK"})
    rpm_limit: int = Field(60, json_schema_extra={"example": 60})
    tpm_limit: int = Field(100000, json_schema_extra={"example": 100000})
    concurrency_limit: int = Field(5, json_schema_extra={"example": 5})
    expires_at: Optional[str] = Field(None, json_schema_extra={"example": "2026-12-31T23:59:59Z"})


class StaffKeyRequest(BaseModel):
    tenant_id: str = Field(..., json_schema_extra={"example": "TENANT_RETAIL_BANK"})
    requested_by: str = Field(..., json_schema_extra={"example": "dev_namle@company.com"})
    justification: str = Field(..., json_schema_extra={"example": "Project Chatbot AI Integration"})
    rpm_limit: int = Field(60, json_schema_extra={"example": 60})
    tpm_limit: int = Field(100000, json_schema_extra={"example": 100000})
    concurrency_limit: int = Field(5, json_schema_extra={"example": 5})


class RejectRequestPayload(BaseModel):
    reason: str = Field(..., json_schema_extra={"example": "Exceeds department quota limit"})


class UpdateQuotaRequest(BaseModel):
    rpm_limit: Optional[int] = Field(None, json_schema_extra={"example": 120}, description="Requests Per Minute limit")
    tpm_limit: Optional[int] = Field(None, json_schema_extra={"example": 200000}, description="Tokens Per Minute limit")
    concurrency_limit: Optional[int] = Field(None, json_schema_extra={"example": 10}, description="Max concurrent requests limit")


# Direct Admin Key Creation API
@router.post("/admin/v1/keys", summary="Create New API Key Direct (Admin Only)")
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


# Staff Key Request API (Creates Pending Approval Request)
@router.post("/v1/key-requests", summary="Submit API Key Request (Staff Self-Service)")
async def submit_key_request(
    request: StaffKeyRequest,
    repo: IKeyRepository = Depends(get_key_repo)
):
    request_id = f"req_{uuid.uuid4().hex[:10]}"
    now = datetime.now(timezone.utc).isoformat()

    record = {
        "request_id": request_id,
        "tenant_id": request.tenant_id,
        "requested_by": request.requested_by,
        "justification": request.justification,
        "rpm_limit": request.rpm_limit,
        "tpm_limit": request.tpm_limit,
        "concurrency_limit": request.concurrency_limit,
        "status": "pending_approval",
        "created_at": now,
    }

    created = await repo.create_key_request(record)
    return {
        "request_id": created["request_id"],
        "status": "pending_approval",
        "message": "API key request submitted successfully. Pending Admin approval.",
    }


# Admin List Pending Key Requests API
@router.get("/admin/v1/key-requests", summary="List Pending Key Requests (Admin Only)")
async def list_pending_key_requests(repo: IKeyRepository = Depends(get_key_repo)):
    pending = await repo.list_pending_key_requests()
    return {"object": "list", "data": pending}


# Admin Approve Key Request API
@router.post("/admin/v1/key-requests/{request_id}/approve", summary="Approve Key Request (Admin Only)")
async def approve_key_request(
    request_id: str,
    repo: IKeyRepository = Depends(get_key_repo)
):
    approved = await repo.approve_key_request(request_id)
    if not approved:
        raise HTTPException(status_code=404, detail="Pending key request ID not found.")

    return {
        "request_id": request_id,
        "status": "approved",
        "key_id": approved["approved_key_id"],
        "api_key_plaintext": approved["api_key_plaintext"],
        "message": f"Key request '{request_id}' approved. API key generated and activated.",
    }


# Admin Reject Key Request API
@router.post("/admin/v1/key-requests/{request_id}/reject", summary="Reject Key Request (Admin Only)")
async def reject_key_request(
    request_id: str,
    payload: RejectRequestPayload,
    repo: IKeyRepository = Depends(get_key_repo)
):
    rejected = await repo.reject_key_request(request_id, payload.reason)
    if not rejected:
        raise HTTPException(status_code=404, detail="Pending key request ID not found.")

    return {
        "request_id": request_id,
        "status": "rejected",
        "reason": payload.reason,
        "message": f"Key request '{request_id}' rejected.",
    }


@router.get("/admin/v1/keys", summary="List All API Keys and Quotas from MongoDB Atlas")
async def list_api_keys(repo: IKeyRepository = Depends(get_key_repo)):
    keys = await repo.list_keys()
    return {"object": "list", "data": keys}


@router.put("/admin/v1/keys/{key_id}/quota", summary="Adjust Quota Limits in MongoDB Atlas")
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


@router.delete("/admin/v1/keys/{key_id}", summary="Delete API Key from MongoDB Atlas")
async def revoke_api_key(key_id: str, repo: IKeyRepository = Depends(get_key_repo)):
    deleted = await repo.delete_key(key_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"API key ID '{key_id}' not found.")

    return {"message": f"API key '{key_id}' deleted from MongoDB Atlas."}
