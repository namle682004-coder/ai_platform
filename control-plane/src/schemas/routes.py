from fastapi import APIRouter, HTTPException
from .registry import schema_registry

router = APIRouter(prefix="/v1", tags=["Dynamic Schema Registry"])


@router.get("/schemas", summary="List All AI Model JSON Schemas")
async def list_model_schemas():
    return {
        "object": "list",
        "schemas": schema_registry.list_schemas(),
    }


@router.get("/schemas/{model_id}", summary="Get JSON Schema for Specific AI Model")
async def get_model_schema(model_id: str):
    schema = schema_registry.get_schema_for_model(model_id)
    if not schema:
        raise HTTPException(status_code=404, detail=f"No schema registered for model '{model_id}'")
    return schema


@router.get("/models/{model_id}/schema", summary="Alias: Get Model Schema")
async def get_model_schema_alias(model_id: str):
    return await get_model_schema(model_id)
