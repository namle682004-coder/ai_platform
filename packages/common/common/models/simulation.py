"""
Domain Entities for Simulation & Playground Experiment Tracking.
Compliant with Clean Architecture DDD.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
import uuid
from pydantic import BaseModel, Field


class SimulationRun(BaseModel):
    """Entity tracking individual interactive playground / sandbox simulation runs."""
    run_id: str = Field(default_factory=lambda: f"sim_{uuid.uuid4().hex[:12]}")
    user_id: str = Field(default="admin@company.com")
    tenant_id: str = Field(default="default")
    project_id: str | None = None
    domain: Literal["chat", "ocr", "vision", "audio", "nlp", "image", "moderation", "general"] = "general"
    model_alias: str
    input_payload: dict[str, Any] = Field(default_factory=dict)
    output_payload: dict[str, Any] = Field(default_factory=dict)
    status: Literal["success", "failed", "running"] = "success"
    latency_ms: float = 0.0
    token_usage: dict[str, int] | None = None
    error_message: str | None = None
    tags: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ModelComparisonRun(BaseModel):
    """Entity tracking side-by-side A/B model comparison tests in playground."""
    comparison_id: str = Field(default_factory=lambda: f"cmp_{uuid.uuid4().hex[:12]}")
    user_id: str = Field(default="admin@company.com")
    domain: str = "chat"
    prompt: str
    model_a_alias: str
    model_a_output: str | dict[str, Any]
    model_a_latency_ms: float = 0.0
    model_b_alias: str
    model_b_output: str | dict[str, Any]
    model_b_latency_ms: float = 0.0
    winner_chosen: Literal["model_a", "model_b", "tie", "none"] = "none"
    feedback_notes: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
