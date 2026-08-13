import uuid
from datetime import datetime

from common.models.schemas import APIKeyCreateRequest, APIKeyResponse
from common.security.argon2_hasher import generate_api_key
from fastapi import APIRouter
from gateway.core.config import gateway_settings

router = APIRouter(prefix="/admin/v1", tags=["Admin - API Key Management"])
_KEYS_STORE: dict[str, dict] = {}


@router.post("/keys", response_model=APIKeyResponse, status_code=201)
async def create_api_key(request: APIKeyCreateRequest):
    key_id = f"key_{uuid.uuid4().hex[:12]}"
    raw_key, hashed_key = generate_api_key(
        prefix="aip_live",
        master_pepper=gateway_settings.master_key_pepper
    )

    record = {
        "id": key_id,
        "name": request.name,
        "tenant_id": request.tenant_id,
        "cost_center": request.cost_center,
        "hashed_key": hashed_key,
        "allowed_aliases": request.allowed_aliases,
        "rpm_limit": request.rpm_limit,
        "tpm_limit": request.tpm_limit,
        "concurrency_limit": request.concurrency_limit,
        "is_active": True,
        "created_at": datetime.utcnow(),
        "expires_at": request.expires_at,
    }

    _KEYS_STORE[key_id] = record
    response_data = record.copy()
    response_data["raw_api_key"] = raw_key
    return APIKeyResponse(**response_data)
