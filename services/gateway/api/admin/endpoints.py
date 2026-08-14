from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/admin/v1", tags=["Admin - API Endpoints Management"])


class EndpointStatusUpdateRequest(BaseModel):
    status: str = Field(..., json_schema_extra={"example": "enabled"}, description="Export Status: 'enabled' or 'disabled'")


_ENDPOINTS_REGISTRY = {
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


def is_endpoint_enabled(endpoint_id: str) -> bool:
    endpoint = _ENDPOINTS_REGISTRY.get(endpoint_id)
    if not endpoint:
        return True
    return endpoint.get("status") == "enabled"


@router.get("/endpoints", summary="List All Exported API Endpoints")
async def list_exported_endpoints():
    return {"object": "list", "data": _ENDPOINTS_REGISTRY}


@router.put("/endpoints/{endpoint_id}", summary="Update API Endpoint Export Status")
async def update_endpoint_export_status(endpoint_id: str, request: EndpointStatusUpdateRequest):
    if endpoint_id not in _ENDPOINTS_REGISTRY:
        raise HTTPException(status_code=404, detail=f"Endpoint '{endpoint_id}' not found.")

    if request.status not in ["enabled", "disabled"]:
        raise HTTPException(status_code=400, detail="Status must be 'enabled' or 'disabled'.")

    _ENDPOINTS_REGISTRY[endpoint_id]["status"] = request.status
    return {
        "message": f"Endpoint '{endpoint_id}' export status updated to '{request.status}'.",
        "endpoint": _ENDPOINTS_REGISTRY[endpoint_id],
    }
