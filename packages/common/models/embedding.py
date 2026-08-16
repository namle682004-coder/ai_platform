from pydantic import BaseModel, Field
from common.models.common import UsageInfo


class EmbeddingRequest(BaseModel):
    model: str = Field(..., json_schema_extra={"example": "embed-standard"})
    input: str | list[str] = Field(..., json_schema_extra={"example": "Embedding Input"})
    user: str | None = None


class EmbeddingData(BaseModel):
    object: str = "embedding"
    index: int = 0
    embedding: list[float]


class EmbeddingResponse(BaseModel):
    object: str = "list"
    data: list[EmbeddingData]
    model: str
    usage: UsageInfo
