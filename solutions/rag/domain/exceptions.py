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


class LLMStreamInterruptedError(LLMGenerationError):
    """
    The runtime cut a streaming answer off part-way because it ran out of room for it next to the other
    requests in flight (llama.cpp: "Context size has been exceeded"). Busy, not broken: the answer can be
    generated again as long as none of the partial text was shown to the user.
    """

    capacity_refusal = True  # runtime guards do not count it as a runtime failure


class SessionNotFoundError(RAGDomainException):
    """Raised when a chat session cannot be found."""
    pass


class ServiceOverloadedError(RAGDomainException):
    """A model runtime is at capacity (or recovering): the request is refused, retry after `retry_after` s."""

    def __init__(self, message: str = "", retry_after: int = 10) -> None:
        super().__init__(message)
        self.retry_after = max(1, int(retry_after))
