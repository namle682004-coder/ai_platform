"""
Pydantic Schemas for AIP TTS Adapter.
"""

from typing import List, Optional
from pydantic import BaseModel, Field


class VoiceInfo(BaseModel):
    voice_id: str
    name: str
    gender: str
    accent: str
    sample_url: Optional[str] = None


class TTSRequest(BaseModel):
    model: str = Field(default="tts-vi-standard", json_schema_extra={"example": "tts-vi-standard"})
    input: str = Field(..., json_schema_extra={"example": "Xin chào, đây là giọng đọc AI."})
    voice: Optional[str] = Field(default="northern_female", json_schema_extra={"example": "northern_female"})
    response_format: str = Field(default="mp3", json_schema_extra={"example": "mp3"})
    speed: float = Field(default=1.0, ge=0.5, le=2.0)


class VoiceListResponse(BaseModel):
    voices: List[VoiceInfo]
