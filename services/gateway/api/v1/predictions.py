from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter(prefix="/v1", tags=["Predictions (Custom Inference)"])


class PredictionRequest(BaseModel):
    alias_name: str = Field(..., json_schema_extra={"example": "translate-vi-standard"})
    payload: dict[str, Any] = Field(default_factory=dict)


@router.post("/predictions")
async def create_prediction(request: PredictionRequest):
    return {
        "status": "success",
        "alias_name": request.alias_name,
        "result": {
            "prediction": "Execution completed by prediction pipeline.",
            "execution_time_ms": 12.4
        }
    }
