"""
Pydantic Schemas for AIP OCR & Document Server.
"""

from typing import List
from pydantic import BaseModel, Field


class BoundingBox(BaseModel):
    box: List[List[float]]
    text: str
    confidence: float


class OCRResponse(BaseModel):
    filename: str
    detected_text: str
    boxes: List[BoundingBox] = Field(default_factory=list)
    execution_time_ms: float = 0.0
