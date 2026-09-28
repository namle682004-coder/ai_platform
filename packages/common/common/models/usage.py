"""
Domain Entities for AI Inference Usage Metering & Token Consumption.
Compliant with Clean Architecture DDD & SRS Section 7 & 8.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional, List
from pydantic import BaseModel, Field


class UsageRecord(BaseModel):
    """Granular inference usage record captured asynchronously per API invocation."""
    usage_id: str = Field(default_factory=lambda: f"usg_{uuid.uuid4().hex[:12]}")
    request_id: str = Field(..., description="Correlated request ID")
    tenant_id: str = Field(default="TENANT_RETAIL_BANK", description="Tenant organization ID")
    cost_center: str = Field(default="CC_DIGITAL_BANKING", description="Cost center / department")
    api_key_prefix: Optional[str] = Field(None, description="Masked API key prefix")
    domain: str = Field(default="chat", description="Inference domain: chat, embedding, audio, vision, etc.")
    model_alias: str = Field(default="chat-general-standard", description="Logical model alias invoked")
    physical_model: str = Field(default="Qwen3-8B", description="Physical base foundation model")
    prompt_tokens: int = Field(default=0, description="Input/prompt token count")
    completion_tokens: int = Field(default=0, description="Output/completion token count")
    total_tokens: int = Field(default=0, description="Total tokens consumed")
    cost_vnd: float = Field(default=0.0, description="Calculated financial cost in VNĐ")
    latency_ms: float = Field(default=0.0, description="Inference latency in milliseconds")
    status_code: int = Field(default=200, description="HTTP response status code")
    stream: bool = Field(default=False, description="Whether SSE streaming mode was used")
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="ISO 8601 UTC timestamp",
    )


class UsageSummary(BaseModel):
    """Aggregated usage metrics summary for tenant or cost center."""
    tenant_id: str
    total_requests: int = 0
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_tokens: int = 0
    total_cost_vnd: float = 0.0
    active_models: List[str] = Field(default_factory=list)
