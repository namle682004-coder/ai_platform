from datetime import datetime
from pydantic import BaseModel, Field


class APIKeyCreateRequest(BaseModel):
    name: str = Field(..., json_schema_extra={"example": "Banking App Primary Key"})
    tenant_id: str = Field(..., json_schema_extra={"example": "TENANT_RETAIL_BANK"})
    cost_center: str = Field(..., json_schema_extra={"example": "CC_DIGITAL_BANKING"})
    allowed_aliases: list[str] = Field(default_factory=lambda: ["*"])
    rpm_limit: int = 60
    tpm_limit: int = 100000
    concurrency_limit: int = 5
    expires_at: datetime | None = None


class APIKeyResponse(BaseModel):
    id: str
    name: str
    tenant_id: str
    cost_center: str
    raw_api_key: str | None = None
    allowed_aliases: list[str]
    rpm_limit: int
    tpm_limit: int
    concurrency_limit: int
    is_active: bool
    created_at: datetime
    expires_at: datetime | None = None
