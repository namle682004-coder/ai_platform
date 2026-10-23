"""
Request / response contracts for the embedding server.

/v1/embeddings follows the OpenAI embeddings schema (plus an optional BGE-M3 sparse output).
/v1/rerank follows the Cohere / Jina / TEI rerank schema.
"""

from __future__ import annotations

from typing import List, Optional, Union

from pydantic import BaseModel, Field


class EmbeddingRequest(BaseModel):
    input: Union[str, List[str]]
    model: Optional[str] = None
    return_sparse: bool = Field(default=False, description="Also return BGE-M3 lexical (sparse) weights")


class SparseVector(BaseModel):
    indices: List[int]
    values: List[float]


class EmbeddingItem(BaseModel):
    object: str = "embedding"
    index: int
    embedding: List[float]
    sparse: Optional[SparseVector] = None


class Usage(BaseModel):
    prompt_tokens: int = 0
    total_tokens: int = 0


class EmbeddingResponse(BaseModel):
    object: str = "list"
    data: List[EmbeddingItem]
    model: str
    usage: Usage


class RerankRequest(BaseModel):
    query: str = Field(..., min_length=1)
    documents: List[str] = Field(..., min_length=1)
    top_n: Optional[int] = Field(default=None, ge=1)
    model: Optional[str] = None
    return_documents: bool = False


class RerankResult(BaseModel):
    index: int
    relevance_score: float
    document: Optional[str] = None


class RerankResponse(BaseModel):
    results: List[RerankResult]
    model: str
    latency_ms: float
