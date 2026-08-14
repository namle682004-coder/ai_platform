from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/admin/v1", tags=["Admin - Model Aliases"])


class AliasStatusUpdateRequest(BaseModel):
    status: str = Field(..., json_schema_extra={"example": "enabled"}, description="Status: 'enabled' or 'disabled'")


_ALIASES_REGISTRY = {
    "chat-general-standard": {"model_name": "Qwen3-8B", "status": "enabled", "runtime": "vllm"},
    "chat-general-high-quality": {"model_name": "Qwen3-14B", "status": "enabled", "runtime": "vllm"},
    "embed-standard": {"model_name": "Qwen3-Embedding-8B", "status": "enabled", "runtime": "vllm"},
    "stt-vn-standard": {"model_name": "PhoWhisper", "status": "enabled", "runtime": "faster-whisper"},
    "tts-vi-standard": {"model_name": "viXTTS", "status": "enabled", "runtime": "tts-adapter"},
}


@router.get("/aliases", summary="List Model Aliases")
async def list_model_aliases():
    return {"object": "list", "data": _ALIASES_REGISTRY}


@router.put("/aliases/{name}", summary="Update Alias Status")
async def update_alias_status(name: str, request: AliasStatusUpdateRequest):
    if name not in _ALIASES_REGISTRY:
        raise HTTPException(status_code=404, detail=f"Alias '{name}' not found.")

    if request.status not in ["enabled", "disabled"]:
        raise HTTPException(status_code=400, detail="Status must be 'enabled' or 'disabled'.")

    _ALIASES_REGISTRY[name]["status"] = request.status
    return {"message": f"Alias '{name}' status updated to '{request.status}'.", "alias": _ALIASES_REGISTRY[name]}
