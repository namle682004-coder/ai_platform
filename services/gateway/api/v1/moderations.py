
from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter(prefix="/v1", tags=["Moderations"])


class ModerationRequest(BaseModel):
    input: str | list[str] = Field(..., json_schema_extra={"example": "Kiem tra noi dung an toan"})
    model: str = Field("moderation-multimodal", json_schema_extra={"example": "moderation-multimodal"})


@router.post("/moderations")
async def create_moderation(payload: ModerationRequest):
    inputs = [payload.input] if isinstance(payload.input, str) else payload.input
    results = [
        {
            "flagged": False,
            "categories": {"hate": False, "harassment": False, "self_harm": False, "sexual": False, "violence": False},
            "category_scores": {"hate": 0.001, "harassment": 0.002, "self_harm": 0.0001, "sexual": 0.001, "violence": 0.003}
        }
        for _ in inputs
    ]
    return {"id": "modr-01HXGWEXAMPLE", "model": payload.model, "results": results}
