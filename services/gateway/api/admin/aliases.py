from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from common.database.mongodb import mongo_manager

router = APIRouter(prefix="/admin/v1", tags=["Admin - Model Aliases"])


class AliasStatusUpdateRequest(BaseModel):
    status: str = Field(..., json_schema_extra={"example": "enabled"}, description="Status: 'enabled' or 'disabled'")


_ALIASES_MEMORY_CACHE = {
    "chat-general-standard": {"model_name": "Qwen3-8B", "status": "enabled", "runtime": "vllm"},
    "chat-general-high-quality": {"model_name": "Qwen3-14B", "status": "enabled", "runtime": "vllm"},
    "embed-standard": {"model_name": "Qwen3-Embedding-8B", "status": "enabled", "runtime": "vllm"},
    "stt-vn-standard": {"model_name": "PhoWhisper", "status": "enabled", "runtime": "faster-whisper"},
    "tts-vi-standard": {"model_name": "viXTTS", "status": "enabled", "runtime": "tts-adapter"},
}


@router.get("/aliases", summary="List Model Aliases from MongoDB Atlas")
async def list_model_aliases():
    db = mongo_manager.get_database()
    if db is not None:
        try:
            cursor = db.aliases.find({}, {"_id": 0})
            aliases_list = await cursor.to_list(length=100)
            if aliases_list:
                formatted = {item["alias_name"]: item for item in aliases_list}
                return {"object": "list", "data": formatted}
        except Exception:
            pass

    return {"object": "list", "data": _ALIASES_MEMORY_CACHE}


@router.put("/aliases/{name}", summary="Update Alias Status in MongoDB Atlas")
async def update_alias_status(name: str, request: AliasStatusUpdateRequest):
    if request.status not in ["enabled", "disabled"]:
        raise HTTPException(status_code=400, detail="Status must be 'enabled' or 'disabled'.")

    db = mongo_manager.get_database()
    if db is not None:
        try:
            result = await db.aliases.update_one(
                {"alias_name": name},
                {"$set": {"status": request.status}}
            )
            if result.matched_count > 0:
                doc = await db.aliases.find_one({"alias_name": name}, {"_id": 0})
                return {"message": f"Alias '{name}' status updated in MongoDB Atlas.", "alias": doc}
        except Exception:
            pass

    if name in _ALIASES_MEMORY_CACHE:
        _ALIASES_MEMORY_CACHE[name]["status"] = request.status
        return {"message": f"Alias '{name}' status updated in memory.", "alias": _ALIASES_MEMORY_CACHE[name]}

    raise HTTPException(status_code=404, detail=f"Alias '{name}' not found.")
