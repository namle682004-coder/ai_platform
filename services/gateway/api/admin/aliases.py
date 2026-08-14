from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from common.interfaces.base import IAliasRepository
from common.repositories.mongo_repositories import alias_repository

router = APIRouter(prefix="/admin/v1", tags=["Admin - Model Aliases"])


def get_alias_repo() -> IAliasRepository:
    return alias_repository


class AliasStatusUpdateRequest(BaseModel):
    status: str = Field(..., json_schema_extra={"example": "enabled"}, description="Status: 'enabled' or 'disabled'")


@router.get("/aliases", summary="List Model Aliases from MongoDB Atlas")
async def list_model_aliases(repo: IAliasRepository = Depends(get_alias_repo)):
    aliases = await repo.list_aliases()
    return {"object": "list", "data": aliases}


@router.put("/aliases/{name}", summary="Update Alias Status in MongoDB Atlas")
async def update_alias_status(
    name: str,
    request: AliasStatusUpdateRequest,
    repo: IAliasRepository = Depends(get_alias_repo)
):
    if request.status not in ["enabled", "disabled"]:
        raise HTTPException(status_code=400, detail="Status must be 'enabled' or 'disabled'.")

    updated = await repo.update_alias_status(name, request.status)
    if not updated:
        raise HTTPException(status_code=404, detail=f"Alias '{name}' not found.")

    return {"message": f"Alias '{name}' status updated in MongoDB Atlas.", "alias": updated}
