"""
Domain Exceptions for AIP Enterprise RAG Solution.
"""

from __future__ import annotations


class RAGDomainException(Exception):
    """Base exception for all RAG domain errors."""
    pass


class DocumentNotFoundError(RAGDomainException):
    """Raised when a requested document does not exist."""
    pass


class DocumentParsingError(RAGDomainException):
    """Raised when parsing document file bytes fails."""
    pass


class ChunkingError(RAGDomainException):
    """Raised when text chunking fails to produce valid tokens."""
    pass


class VectorStoreError(RAGDomainException):
    """Raised when vector indexing or querying encounters errors."""
    pass


class EmbeddingError(RAGDomainException):
    """Raised when embedding model inference fails."""
    pass


class RerankerError(RAGDomainException):
    """Raised when the cross-encoder reranking runtime is unavailable or returns invalid scores."""
    pass


class LLMGenerationError(RAGDomainException):
    """Raised when upstream LLM response fails."""
    pass


class SessionNotFoundError(RAGDomainException):
    """Raised when a chat session cannot be found."""
    pass
