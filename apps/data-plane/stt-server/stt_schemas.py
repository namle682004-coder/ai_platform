"""
Pydantic Schemas for AIP STT Server (Faster-Whisper).
"""

from typing import List, Optional
from pydantic import BaseModel, Field


class TranscriptionWord(BaseModel):
    word: str
    start: float
    end: float
    probability: float = 1.0


class TranscriptionSegment(BaseModel):
    id: int
    seek: int = 0
    start: float
    end: float
    text: str
    tokens: List[int] = Field(default_factory=list)
    temperature: float = 0.0
    avg_logprob: float = -0.5
    compression_ratio: float = 1.0
    no_speech_prob: float = 0.0
    words: Optional[List[TranscriptionWord]] = None


class TranscriptionResponse(BaseModel):
    text: str
    language: str = "vi"
    duration: float = 0.0
    segments: List[TranscriptionSegment] = Field(default_factory=list)
