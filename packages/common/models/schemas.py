from datetime import datetime
from typing import Any, Dict, List, Literal, Optional, Union
from pydantic import BaseModel, Field


class AIPError(BaseModel):
    type: str = Field("invalid_request_error", json_schema_extra={"example": "invalid_request_error"})
    code: str = Field(..., json_schema_extra={"example": "rate_limit_exceeded"})
    message: str = Field(..., json_schema_extra={"example": "Rate limit exceeded."})
    request_id: Optional[str] = Field(None, json_schema_extra={"example": "req_01HX12345"})
    retryable: bool = Field(False, json_schema_extra={"example": False})


class AIPErrorResponse(BaseModel):
    error: AIPError


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant", "function", "tool"] = Field(..., json_schema_extra={"example": "user"})
    content: str = Field(..., json_schema_extra={"example": "Hello, AI Platform!"})
    name: Optional[str] = None


class ChatCompletionRequest(BaseModel):
    model: str = Field(..., json_schema_extra={"example": "chat-general-standard"})
    messages: List[ChatMessage]
    temperature: Optional[float] = Field(0.7, ge=0.0, le=2.0)
    top_p: Optional[float] = Field(1.0, ge=0.0, le=1.0)
    n: Optional[int] = Field(1, ge=1, le=5)
    stream: bool = Field(False, json_schema_extra={"example": False})
    max_tokens: Optional[int] = Field(None, ge=1)
    user: Optional[str] = None


class ChatCompletionChoice(BaseModel):
    index: int = 0
    message: ChatMessage
    finish_reason: Optional[str] = "stop"


class UsageInfo(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ChatCompletionResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: List[ChatCompletionChoice]
    usage: UsageInfo


class EmbeddingRequest(BaseModel):
    model: str = Field(..., json_schema_extra={"example": "embed-standard"})
    input: Union[str, List[str]] = Field(..., json_schema_extra={"example": "Embedding Input"})
    user: Optional[str] = None


class EmbeddingData(BaseModel):
    object: str = "embedding"
    index: int = 0
    embedding: List[float]


class EmbeddingResponse(BaseModel):
    object: str = "list"
    data: List[EmbeddingData]
    model: str
    usage: UsageInfo


class JobCreateRequest(BaseModel):
    job_type: str = Field(..., json_schema_extra={"example": "video_generation"})
    alias_name: str = Field(..., json_schema_extra={"example": "video-gen-standard"})
    payload: Dict[str, Any] = Field(default_factory=dict)
    webhook_url: Optional[str] = None


class JobStatusResponse(BaseModel):
    job_id: str
    job_type: str
    alias_name: str
    status: Literal["queued", "running", "completed", "failed", "cancelled", "expired"]
    progress: int = Field(0, ge=0, le=100)
    error_message: Optional[str] = None
    result_urls: Optional[List[str]] = None
    created_at: datetime
    updated_at: datetime


class APIKeyCreateRequest(BaseModel):
    name: str = Field(..., json_schema_extra={"example": "Banking App Primary Key"})
    tenant_id: str = Field(..., json_schema_extra={"example": "TENANT_RETAIL_BANK"})
    cost_center: str = Field(..., json_schema_extra={"example": "CC_DIGITAL_BANKING"})
    allowed_aliases: List[str] = Field(default_factory=lambda: ["*"])
    rpm_limit: int = 60
    tpm_limit: int = 100000
    concurrency_limit: int = 5
    expires_at: Optional[datetime] = None


class APIKeyResponse(BaseModel):
    id: str
    name: str
    tenant_id: str
    cost_center: str
    raw_api_key: Optional[str] = None
    allowed_aliases: List[str]
    rpm_limit: int
    tpm_limit: int
    concurrency_limit: int
    is_active: bool
    created_at: datetime
    expires_at: Optional[datetime] = None
