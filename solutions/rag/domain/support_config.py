"""
Domain port and DTOs for per-tenant Support & Escalation Configuration (Requirement #17).
Hotline, remote support channels (UltraViewer/TeamViewer), and contact instructions.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Protocol
from pydantic import BaseModel, Field


class SupportConfigDTO(BaseModel):
    tenant_id: str
    hotline: str = Field(default="", description="Hotline phone number (e.g. 1900 xxxx, 0262 xxx xxx)")
    support_method: str = Field(default="", description="Remote support channel (e.g. UltraViewer, TeamViewer)")
    instructions: str = Field(default="", description="Instructions (e.g. cung cấp ID, mật khẩu đọc qua điện thoại)")
    updated_at: Optional[int] = None


class SupportConfigUpdateRequest(BaseModel):
    hotline: Optional[str] = Field(default="", description="Hotline phone number")
    support_method: Optional[str] = Field(default="", description="Remote support channel")
    instructions: Optional[str] = Field(default="", description="Instructions for remote support")


class SupportRepositoryPort(Protocol):
    async def get_support_config(self, tenant_id: str) -> Optional[Dict[str, Any]]:
        ...

    async def save_support_config(
        self, tenant_id: str, hotline: str, support_method: str, instructions: str
    ) -> Dict[str, Any]:
        ...
