from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from common.interfaces.base import IEndpointRepository
from common.repositories.mongo_repositories import endpoint_repository

router = APIRouter(prefix="/admin/v1", tags=["Admin - API Endpoints Management"])


def get_endpoint_repo() -> IEndpointRepository:
    return endpoint_repository


class EndpointStatusUpdateRequest(BaseModel):
    status: str = Field(..., json_schema_extra={"example": "enabled"}, description="Export Status: 'enabled' or 'disabled'")


def is_endpoint_enabled(endpoint_id: str) -> bool:
    cache = getattr(endpoint_repository, "_endpoints_cache", None)
    if cache is None:
        cache = getattr(endpoint_repository, "_memory_cache", {})
    endpoint = cache.get(endpoint_id)
    if not endpoint:
        return True
    return endpoint.get("status") in ["enabled", "active"]


@router.get("/endpoints", summary="List All Exported API Endpoints from MongoDB Atlas")
async def list_exported_endpoints(repo: IEndpointRepository = Depends(get_endpoint_repo)):
    endpoints = await repo.list_endpoints()
    return {"object": "list", "data": endpoints}


@router.put("/endpoints/{endpoint_id}", summary="Update API Endpoint Export Status in MongoDB Atlas")
async def update_endpoint_export_status(
    endpoint_id: str,
    request: EndpointStatusUpdateRequest,
    repo: IEndpointRepository = Depends(get_endpoint_repo)
):
    if request.status not in ["enabled", "disabled"]:
        raise HTTPException(status_code=400, detail="Status must be 'enabled' or 'disabled'.")

    normalized_id = endpoint_id
    if normalized_id == "chat_completions":
        normalized_id = "/v1/chat/completions"

    updated = await repo.update_endpoint_status(normalized_id, request.status)
    if not updated:
        raise HTTPException(status_code=404, detail=f"Endpoint '{endpoint_id}' not found.")

    return {
        "message": f"Endpoint '{endpoint_id}' status updated in MongoDB Atlas.",
        "endpoint": updated,
    }
