"""
Abstract Protocol & DTOs for RAG Benchmark Adapters.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol
from pydantic import BaseModel


class NormalizedResponse(BaseModel):
    answer: str
    retrieved_chunks: List[Dict[str, Any]] = []
    citations: List[Dict[str, Any]] = []
    latency_ms: float = 0.0
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    usage: Optional[Dict[str, Any]] = None
    route_taken: Optional[str] = None
    intent: Optional[str] = None


class RAGAdapter(Protocol):
    """Protocol implemented by Local, Fixed-Context, and External API adapters."""
    async def answer(
        self,
        question: str,
        *,
        context: Optional[List[Dict[str, Any]]] = None,
        top_k: int = 5,
    ) -> NormalizedResponse:
        ...
