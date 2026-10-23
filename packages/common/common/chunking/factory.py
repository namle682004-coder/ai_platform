"""
Factory for instantiating specialized chunkers based on document domain and RAG strategy.
Compliant with Enterprise RAG Architecture standards.
"""

from __future__ import annotations

from typing import Any

from .base import BaseChunker
from .recursive_chunker import RecursiveChunker
from .semantic_chunker import SemanticChunker
from .structure_chunker import StructureChunker
from .token_chunker import TextChunker, TokenChunker


class ChunkerFactory:
    """Factory creating appropriate Chunker strategy."""

    @staticmethod
    def create(strategy: str = "hybrid", **kwargs: Any) -> BaseChunker:
        normalized = strategy.lower().strip()
        if normalized in ("hybrid", "default", "token"):
            return TokenChunker(**kwargs)
        elif normalized in ("recursive", "langchain"):
            return RecursiveChunker(**kwargs)
        elif normalized in ("structure", "structural", "markdown"):
            return StructureChunker(**kwargs)
        elif normalized in ("semantic", "sentence"):
            return SemanticChunker(**kwargs)
        elif normalized in ("text", "plain"):
            return TextChunker(**kwargs)
        else:
            return TokenChunker(**kwargs)
