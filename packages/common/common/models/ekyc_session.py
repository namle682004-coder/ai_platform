"""
Domain Entities for eKYC Biometric Verification (FaceMatch 1:1 & Liveness Anti-Spoofing).
Compliant with Clean Architecture DDD.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
import uuid
from pydantic import BaseModel, Field


class EKYCVerificationSession(BaseModel):
    """Entity storing an eKYC biometric verification session."""
    session_id: str = Field(default_factory=lambda: f"ekyc_{uuid.uuid4().hex[:12]}")
    user_id: str = Field(default="admin@company.com")
    tenant_id: str = Field(default="default")
    id_card_image_url: str
    selfie_image_url: str
    facematch_score: float = Field(0.0, ge=0.0, le=100.0)
    liveness_score: float = Field(0.0, ge=0.0, le=100.0)
    is_live: bool = True
    decision: Literal["approved", "rejected", "manual_review"] = "approved"
    metadata: dict[str, Any] = Field(default_factory=dict)
    latency_ms: float = 0.0
    verified_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
