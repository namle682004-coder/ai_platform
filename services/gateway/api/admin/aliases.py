from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional

router = APIRouter(prefix="/admin/v1", tags=["Admin - Alias Registry & Activation Approval"])

_ALIASES_STORE: dict[str, dict] = {
    "chat-general-standard": {
        "alias_name": "chat-general-standard",
        "physical_model": "Qwen3-8B",
        "runtime_type": "vllm",
        "version": "v1.0",
        "min_vram_gb": 24,
        "is_active": True,
        "canary_percent": 0.0,
        "approval_status": "approved",
    }
}


class AliasCreateRequest(BaseModel):
    alias_name: str = Field(..., json_schema_extra={"example": "chat-finance-v1"})
    physical_model: str = Field(..., json_schema_extra={"example": "Qwen3-14B"})
    runtime_type: str = Field(..., json_schema_extra={"example": "vllm"})
    version: str = Field("v1.0", json_schema_extra={"example": "v1.0"})
    min_vram_gb: int = 32
    auto_approve: bool = Field(False, json_schema_extra={"example": False})  # Default requires Admin Approval!
    canary_percent: float = Field(0.0, ge=0.0, le=100.0)


@router.get("/aliases")
async def list_aliases():
    """List all registered model aliases and their approval / active status."""
    return list(_ALIASES_STORE.values())


@router.post("/aliases", status_code=201)
async def register_alias(request: AliasCreateRequest):
    """Register a new model alias. By default created in DRAFT status requiring Admin Approval."""
    is_active = request.auto_approve
    approval_status = "approved" if request.auto_approve else "pending_approval"

    alias_entry = {
        "alias_name": request.alias_name,
        "physical_model": request.physical_model,
        "runtime_type": request.runtime_type,
        "version": request.version,
        "min_vram_gb": request.min_vram_gb,
        "is_active": is_active,
        "canary_percent": request.canary_percent,
        "approval_status": approval_status,
    }
    _ALIASES_STORE[request.alias_name] = alias_entry
    return alias_entry


@router.post("/aliases/{alias_name}/activate")
async def approve_and_activate_alias(alias_name: str):
    """Admin Approval Endpoint: Approve and publish dynamic export for a model alias."""
    if alias_name not in _ALIASES_STORE:
        raise HTTPException(status_code=404, detail=f"Alias '{alias_name}' not found.")

    _ALIASES_STORE[alias_name]["is_active"] = True
    _ALIASES_STORE[alias_name]["approval_status"] = "approved"
    return {
        "message": f"Alias '{alias_name}' approved and ACTIVATED for export successfully.",
        "alias": _ALIASES_STORE[alias_name]
    }


@router.post("/aliases/{alias_name}/deactivate")
async def deactivate_alias(alias_name: str):
    """Admin Endpoint: Deactivate and stop export for a model alias."""
    if alias_name not in _ALIASES_STORE:
        raise HTTPException(status_code=404, detail=f"Alias '{alias_name}' not found.")

    _ALIASES_STORE[alias_name]["is_active"] = False
    _ALIASES_STORE[alias_name]["approval_status"] = "deactivated"
    return {
        "message": f"Alias '{alias_name}' DEACTIVATED successfully.",
        "alias": _ALIASES_STORE[alias_name]
    }


@router.delete("/aliases/{alias_name}", status_code=204)
async def delete_alias(alias_name: str):
    if alias_name not in _ALIASES_STORE:
        raise HTTPException(status_code=404, detail="Alias not found")
    del _ALIASES_STORE[alias_name]
    return None
