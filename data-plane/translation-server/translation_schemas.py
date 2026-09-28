"""
Pydantic Request & Response Schemas for AIP Translation Server.
Compliant with Clean Architecture Data-Plane & SRS Section 2.3 & 6.1.
"""

import time
import uuid
from typing import List, Optional
from pydantic import BaseModel, Field


class TranslationRequest(BaseModel):
    text: str = Field(..., json_schema_extra={"example": "Xin chào thế giới"})
    source_lang: str = Field(default="vie_Latn", json_schema_extra={"example": "vie_Latn"})
    target_lang: str = Field(default="eng_Latn", json_schema_extra={"example": "eng_Latn"})
    beam_size: Optional[int] = Field(default=None, ge=1, le=10)


class BatchTranslationRequest(BaseModel):
    texts: List[str]
    source_lang: str = "vie_Latn"
    target_lang: str = "eng_Latn"
    beam_size: Optional[int] = 4


class TranslationUsage(BaseModel):
    prompt_tokens: int = Field(..., description="Number of tokens in source text input")
    completion_tokens: int = Field(..., description="Number of tokens generated in translation")
    total_tokens: int = Field(..., description="Total token count (prompt + completion)")
    character_count: int = Field(..., description="Total characters in input string")
    word_count: int = Field(..., description="Total words in input string")


class TranslationMetadata(BaseModel):
    backend: str = Field(..., description="Runtime translation backend")
    device: str = Field(..., description="Target compute accelerator (cuda / cpu)")
    compute_type: str = Field(..., description="Quantization precision (int8 / float16)")
    beam_size: int = Field(..., description="Beam size used for decoding")
    repetition_penalty: float = Field(1.2, description="Penalty for repeated ngrams")
    no_repeat_ngram_size: int = Field(3, description="N-gram repetition suppression window")
    latency_ms: float = Field(..., description="Inference latency in milliseconds")


class TranslationResponse(BaseModel):
    id: str = Field(default_factory=lambda: f"trans_{uuid.uuid4().hex[:12]}")
    object: str = "nlp.translation"
    created: int = Field(default_factory=lambda: int(time.time()))
    status: str = "success"
    model: str
    translated_text: str
    source_lang: str
    target_lang: str
    usage: TranslationUsage
    metadata: TranslationMetadata


class BatchTranslationResponse(BaseModel):
    id: str = Field(default_factory=lambda: f"batch_trans_{uuid.uuid4().hex[:12]}")
    object: str = "nlp.translation.batch"
    created: int = Field(default_factory=lambda: int(time.time()))
    status: str = "success"
    model: str
    translations: List[str]
    source_lang: str
    target_lang: str
    total_execution_time_ms: float
    total_tokens: int
