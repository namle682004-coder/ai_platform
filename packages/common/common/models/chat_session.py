"""
Domain Entities for Multi-Turn Chat Sessions, Messages & Prompt Templates.
Compliant with Clean Architecture DDD.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal
import uuid
from pydantic import BaseModel, Field


class ChatMessageRecord(BaseModel):
    """Single turn message in a conversation session."""
    message_id: str = Field(default_factory=lambda: f"msg_{uuid.uuid4().hex[:12]}")
    session_id: str
    role: Literal["user", "assistant", "system"]
    content: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: float = 0.0
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ConversationSession(BaseModel):
    """Multi-turn chat session thread persisted per user/project."""
    session_id: str = Field(default_factory=lambda: f"cs_{uuid.uuid4().hex[:12]}")
    user_id: str = Field(default="admin@company.com")
    tenant_id: str = Field(default="default")
    project_id: str | None = None
    title: str = Field(default="New Conversation")
    model_alias: str = Field(default="chat-general-standard")
    system_prompt: str | None = None
    temperature: float = 0.7
    max_tokens: int = 1024
    message_count: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PromptTemplate(BaseModel):
    """User-saved reusable prompt template with placeholders."""
    template_id: str = Field(default_factory=lambda: f"tmpl_{uuid.uuid4().hex[:12]}")
    user_id: str = Field(default="admin@company.com")
    title: str
    category: str = Field(default="general")
    template_content: str
    variables: list[str] = Field(default_factory=list)
    is_public: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PromptEvaluationFeedback(BaseModel):
    """User rating / RLHF evaluation feedback on model responses."""
    feedback_id: str = Field(default_factory=lambda: f"fb_{uuid.uuid4().hex[:12]}")
    message_id: str
    user_id: str = Field(default="admin@company.com")
    rating: int = Field(ge=1, le=5)
    feedback_text: str | None = None
    corrected_output: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
