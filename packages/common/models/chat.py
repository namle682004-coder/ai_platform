from typing import Literal
from pydantic import BaseModel, Field
from common.models.common import UsageInfo


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant", "function", "tool"] = Field(..., json_schema_extra={"example": "user"})
    content: str = Field(..., json_schema_extra={"example": "Hello, AI Platform!"})
    name: str | None = None


class ChatCompletionRequest(BaseModel):
    model: str = Field(..., json_schema_extra={"example": "chat-general-standard"})
    messages: list[ChatMessage]
    temperature: float | None = Field(0.7, ge=0.0, le=2.0)
    top_p: float | None = Field(1.0, ge=0.0, le=1.0)
    n: int | None = Field(1, ge=1, le=5)
    stream: bool = Field(False, json_schema_extra={"example": False})
    max_tokens: int | None = Field(None, ge=1)
    user: str | None = None


class ChatCompletionChoice(BaseModel):
    index: int = 0
    message: ChatMessage
    finish_reason: str | None = "stop"


class ChatCompletionResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: list[ChatCompletionChoice]
    usage: UsageInfo
