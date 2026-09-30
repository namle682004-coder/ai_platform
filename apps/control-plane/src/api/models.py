"""
Enterprise Models & Aliases Endpoint compliant with SRS Section 5.2 & Section 6.1.
"""

from fastapi import APIRouter, HTTPException, Request
from src.items.alias_router import alias_router

router = APIRouter(prefix="/v1", tags=["Models & Aliases"])


@router.get("/models", summary="List Available Model Aliases (Scoped to API Key)")
async def list_models(request: Request):
    """
    Returns list of active AI model aliases accessible by the client's API Key.
    """
    allowed_aliases = getattr(request.state, "allowed_aliases", ["*"])
    models_data = await alias_router.list_aliases(allowed_aliases)
    return {
        "object": "list",
        "data": models_data,
    }


@router.get("/models/status", summary="Status of Models Hosted on vLLM Engine")
async def get_models_status():
    from src.status.health import _build_models_status

    return await _build_models_status()


@router.get("/models/{alias}", summary="Retrieve Model Alias Metadata & Specs")
async def get_model_alias(alias: str, request: Request):
    """
    Retrieves granular specs, min VRAM, runtime engine, and status for a specific alias.
    """
    allowed_aliases = getattr(request.state, "allowed_aliases", ["*"])
    if "*" not in allowed_aliases and alias not in allowed_aliases:
        raise HTTPException(
            status_code=403,
            detail=f"Access to alias '{alias}' is forbidden for this API key."
        )

    resolved = await alias_router.resolve_alias(alias)
    if not resolved:
        raise HTTPException(
            status_code=404,
            detail=f"Model alias '{alias}' not found or currently disabled."
        )

    # SRS Section 6.2: Deprecated Aliases flag
    if resolved.get("status") == "deprecated":
        request.state.alias_deprecated = True

    return {
        "id": resolved["alias"],
        "object": "model",
        "created": 1770970000,
        "owned_by": "aip-platform",
        "physical_model": resolved["physical_model"],
        "runtime": resolved["runtime"],
        "namespace": resolved["namespace"],
        "min_vram_gb": resolved["min_vram_gb"],
        "timeout_seconds": resolved["timeout_seconds"],
        "status": resolved["status"],
        "version": resolved["version"],
        "category": resolved["category"],
        "description": resolved["description"],
        "stream_capable": resolved["stream_capable"],
    }
