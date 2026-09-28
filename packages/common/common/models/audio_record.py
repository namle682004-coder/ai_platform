"""
Domain Entities for Speech-to-Text Transcriptions and Text-to-Speech Syntheses.
Compliant with Clean Architecture DDD.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
import uuid
from pydantic import BaseModel, Field


class AudioTranscriptionRecord(BaseModel):
    """Entity storing Speech-to-Text audio transcriptions."""
    record_id: str = Field(default_factory=lambda: f"stt_{uuid.uuid4().hex[:12]}")
    user_id: str = Field(default="admin@company.com")
    tenant_id: str = Field(default="default")
    audio_url: str
    duration_seconds: float = 0.0
    sample_rate: int = 16000
    transcription_text: str
    word_timestamps: list[dict[str, Any]] = Field(default_factory=list)
    language_detected: str = "vi"
    confidence: float = 1.0
    latency_ms: float = 0.0
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AudioSynthesisRecord(BaseModel):
    """Entity storing Text-to-Speech generated voice syntheses."""
    record_id: str = Field(default_factory=lambda: f"tts_{uuid.uuid4().hex[:12]}")
    user_id: str = Field(default="admin@company.com")
    tenant_id: str = Field(default="default")
    input_text: str
    voice_id: str = "northern-female"
    speed: float = 1.0
    pitch: float = 1.0
    output_audio_url: str
    audio_format: str = "mp3"
    duration_seconds: float = 0.0
    latency_ms: float = 0.0
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
