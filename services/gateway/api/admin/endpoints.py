
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/admin/v1", tags=["Admin - API Export & Feature Flags Management"])

# Registry of exported endpoints and their dynamic state (Enabled / Disabled)
_ENDPOINTS_REGISTRY: dict[str, dict] = {
    "v1_chat_completions": {
        "id": "v1_chat_completions",
        "name": "Chat Completions API",
        "path": "/v1/chat/completions",
        "method": "POST",
        "status": "enabled",
        "category": "public_inference",
        "description": "LLM/VLM Chat and Completion endpoint"
    },
    "v1_completions": {
        "id": "v1_completions",
        "name": "Legacy Text Completions API",
        "path": "/v1/completions",
        "method": "POST",
        "status": "enabled",
        "category": "public_inference",
        "description": "Legacy text completion prompt endpoint"
    },
    "v1_embeddings": {
        "id": "v1_embeddings",
        "name": "Vector Embeddings API",
        "path": "/v1/embeddings",
        "method": "POST",
        "status": "enabled",
        "category": "public_inference",
        "description": "Text vector embedding generation endpoint"
    },
    "v1_audio_transcriptions": {
        "id": "v1_audio_transcriptions",
        "name": "Speech-to-Text API",
        "path": "/v1/audio/transcriptions",
        "method": "POST",
        "status": "enabled",
        "category": "public_inference",
        "description": "Audio speech transcription endpoint"
    },
    "v1_audio_speech": {
        "id": "v1_audio_speech",
        "name": "Text-to-Speech API",
        "path": "/v1/audio/speech",
        "method": "POST",
        "status": "enabled",
        "category": "public_inference",
        "description": "Text-to-speech audio synthesis endpoint"
    },
    "v1_images_generations": {
        "id": "v1_images_generations",
        "name": "Text-to-Image Generation API",
        "path": "/v1/images/generations",
        "method": "POST",
        "status": "enabled",
        "category": "public_inference",
        "description": "Diffusion image generation endpoint"
    },
    "v1_moderations": {
        "id": "v1_moderations",
        "name": "Content Moderation API",
        "path": "/v1/moderations",
        "method": "POST",
        "status": "enabled",
        "category": "public_inference",
        "description": "Content safety moderation endpoint"
    },
    "v1_predictions": {
        "id": "v1_predictions",
        "name": "Custom Predictions API",
        "path": "/v1/predictions",
        "method": "POST",
        "status": "enabled",
        "category": "public_inference",
        "description": "Custom model inference endpoint"
    },
    "v1_jobs": {
        "id": "v1_jobs",
        "name": "Async Jobs API",
        "path": "/v1/jobs",
        "method": "POST",
        "status": "enabled",
        "category": "public_inference",
        "description": "Asynchronous heavy job processing endpoint"
    },
}


class EndpointStatusUpdateRequest(BaseModel):
    status: str = Field(..., json_schema_extra={"example": "disabled"})  # "enabled" or "disabled"


def is_endpoint_enabled(path: str) -> bool:
    """Helper function used by Middleware to check if an API path is currently exported & enabled."""
    for ep in _ENDPOINTS_REGISTRY.values():
        if ep["path"] == path:
            return ep["status"] == "enabled"
    return True


@router.get("/endpoints", tags=["Admin - API Export & Feature Flags Management"])
async def list_exported_endpoints():
    """List all registered API endpoints and their current export status (enabled/disabled)."""
    return {
        "object": "list",
        "data": list(_ENDPOINTS_REGISTRY.values())
    }


@router.post("/endpoints/{endpoint_id}/enable", tags=["Admin - API Export & Feature Flags Management"])
async def enable_endpoint(endpoint_id: str):
    """Dynamically start/enable exporting an API endpoint without restarting server."""
    if endpoint_id not in _ENDPOINTS_REGISTRY:
        raise HTTPException(status_code=404, detail=f"Endpoint '{endpoint_id}' not found.")
    _ENDPOINTS_REGISTRY[endpoint_id]["status"] = "enabled"
    return {"message": f"Endpoint '{endpoint_id}' is now ENABLED and exported.", "endpoint": _ENDPOINTS_REGISTRY[endpoint_id]}


@router.post("/endpoints/{endpoint_id}/disable", tags=["Admin - API Export & Feature Flags Management"])
async def disable_endpoint(endpoint_id: str):
    """Dynamically stop/disable exporting an API endpoint (returns 503 Service Unavailable to clients)."""
    if endpoint_id not in _ENDPOINTS_REGISTRY:
        raise HTTPException(status_code=404, detail=f"Endpoint '{endpoint_id}' not found.")
    _ENDPOINTS_REGISTRY[endpoint_id]["status"] = "disabled"
    return {"message": f"Endpoint '{endpoint_id}' is now DISABLED (stop exported).", "endpoint": _ENDPOINTS_REGISTRY[endpoint_id]}
