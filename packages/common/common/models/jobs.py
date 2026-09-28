from datetime import datetime
from typing import Any, Literal
from pydantic import BaseModel, Field


class JobCreateRequest(BaseModel):
    job_type: str = Field(..., json_schema_extra={"example": "video_generation"})
    alias_name: str = Field(..., json_schema_extra={"example": "video-gen-standard"})
    payload: dict[str, Any] = Field(default_factory=dict)
    webhook_url: str | None = None


class JobStatusResponse(BaseModel):
    job_id: str
    job_type: str
    alias_name: str
    status: Literal["queued", "running", "completed", "failed", "cancelled", "expired"]
    progress: int = Field(0, ge=0, le=100)
    error_message: str | None = None
    result_urls: list[str] | None = None
    created_at: datetime
    updated_at: datetime
