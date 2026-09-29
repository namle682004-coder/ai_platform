"""
Pydantic Schemas for AIP Content Moderation Server.
"""

from typing import Dict, List, Union
from pydantic import BaseModel, Field


class ModerationRequest(BaseModel):
    input: Union[str, List[str]] = Field(..., json_schema_extra={"example": "Kiem tra noi dung nay"})
    model: str = Field(default="moderation-multimodal", json_schema_extra={"example": "moderation-multimodal"})


class CategoryScores(BaseModel):
    hate: float = 0.001
    harassment: float = 0.002
    self_harm: float = 0.0001
    sexual: float = 0.001
    violence: float = 0.003
    profanity: float = 0.0001
    pii_leakage: float = 0.0005
    prompt_injection: float = 0.0002


class ModerationResult(BaseModel):
    flagged: bool = False
    categories: Dict[str, bool] = Field(default_factory=lambda: {
        "hate": False,
        "harassment": False,
        "self_harm": False,
        "sexual": False,
        "violence": False,
        "profanity": False,
        "pii_leakage": False,
        "prompt_injection": False,
    })
    category_scores: CategoryScores = Field(default_factory=CategoryScores)


class ModerationResponse(BaseModel):
    id: str = "modr-01HXEXAMPLE"
    model: str
    results: List[ModerationResult]
