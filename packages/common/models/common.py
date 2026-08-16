from pydantic import BaseModel, Field


class AIPError(BaseModel):
    type: str = Field("invalid_request_error", json_schema_extra={"example": "invalid_request_error"})
    code: str = Field(..., json_schema_extra={"example": "rate_limit_exceeded"})
    message: str = Field(..., json_schema_extra={"example": "Rate limit exceeded."})
    request_id: str | None = Field(None, json_schema_extra={"example": "req_01HX12345"})
    retryable: bool = Field(False, json_schema_extra={"example": False})


class AIPErrorResponse(BaseModel):
    error: AIPError


class UsageInfo(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
