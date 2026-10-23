"""
Domain Ports (Interface Abstractions) for AIP Enterprise RAG Solution.
Adheres strictly to the Dependency Inversion Principle of Clean Architecture.
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple, Union

from .entities import (
    DEFAULT_TENANT_ID,
    ChatMessage,
    ChatSession,
    Document,
    DocumentChunk,
    DocumentStatus,
    ParsedDocument,
    RetrievalCandidate,
)

CandidateType = Union[Dict[str, Any], RetrievalCandidate]


class VectorStorePort(ABC):
    """Port for Vector Database interactions (Qdrant, Milvus, etc.)."""

    @abstractmethod
    async def ensure_collection(self) -> None:
        """Provision collection schema, vectors, and payload indexes."""
        ...

    @abstractmethod
    async def upsert_chunks(
        self,
        chunks: List[DocumentChunk],
        vectors: List[List[float]],
        tenant_id: str,
        title: str,
        filename: Optional[str] = None,
        file_type: Optional[str] = None,
        department: Optional[str] = None,
        allowed_roles: Optional[List[str]] = None,
    ) -> int:
        """Index embedded chunks with multi-tenant metadata into vector store."""
        ...

    @abstractmethod
    async def search(
        self,
        query_vector: List[float],
        tenant_id: str,
        query_text: Optional[str] = None,
        user_role: str = "user",
        department: Optional[str] = None,
        doc_ids: Optional[List[str]] = None,
        content_type: Optional[str] = None,
        heading_path: Optional[str] = None,
        top_k: int = 5,
        hybrid: bool = True,
    ) -> List[Dict[str, Any]]:
        """Retrieve candidate vectors with tenant and role ACL isolation, supporting hybrid dense+sparse RRF."""
        ...

    @abstractmethod
    async def delete_by_doc_id(self, doc_id: str, tenant_id: str) -> bool:
        """Remove all points associated with a document."""
        ...

    async def delete_stale_chunks(self, doc_id: str, tenant_id: str, keep_count: int) -> bool:
        """
        Remove points of a re-indexed document whose chunk_index >= keep_count.
        Default falls back to a full delete for adapters without range deletes.
        """
        if keep_count <= 0:
            return await self.delete_by_doc_id(doc_id, tenant_id)
        return True


class EmbeddingPort(ABC):
    """Port for Vector Embedding runtime services (gRPC, Triton, vLLM)."""

    @abstractmethod
    async def get_embedding(self, text: str, model_alias: str = "embed-standard") -> List[float]:
        """Obtain dense vector for a single query text."""
        ...

    @abstractmethod
    async def batch_get_embeddings(
        self,
        texts: List[str],
        model_alias: str = "embed-standard",
    ) -> List[List[float]]:
        """Obtain dense vectors for batch of chunks."""
        ...


class LLMPort(ABC):
    """Port for Large Language Model generation and token streaming."""

    @abstractmethod
    async def generate(
        self,
        messages: List[Dict[str, str]],
        model: str,
        temperature: float = 0.2,
        max_tokens: int = 1024,
        authorization: Optional[str] = None,
    ) -> Tuple[str, int, int]:
        """Generate response text and return (content, prompt_tokens, completion_tokens)."""
        ...

    @abstractmethod
    def stream_generate(
        self,
        messages: List[Dict[str, str]],
        model: str,
        temperature: float = 0.2,
        max_tokens: int = 1024,
        authorization: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """Stream response tokens as an asynchronous generator."""
        ...


class DocumentRepositoryPort(ABC):
    """Port for Document metadata persistence (MongoDB/PostgreSQL)."""

    @abstractmethod
    async def get_document(self, doc_id: str) -> Optional[Dict[str, Any]]:
        """Fetch document record by doc_id."""
        ...

    @abstractmethod
    async def create_document(self, doc_data: Dict[str, Any]) -> str:
        """Insert new document record and return doc_id."""
        ...

    @abstractmethod
    async def update_document_status(
        self,
        doc_id: str,
        status: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Update lifecycle status and stats."""
        ...

    @abstractmethod
    async def list_documents(
        self,
        tenant_id: str,
        department: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """List documents with pagination and tenant filtering."""
        ...

    @abstractmethod
    async def delete_document(self, doc_id: str, tenant_id: str) -> bool:
        """Permanently delete document record."""
        ...


class SessionRepositoryPort(ABC):
    """Port for Chat Session & History persistence."""

    @abstractmethod
    async def get_session(self, session_id: str, user_id: str, tenant_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve complete session history with messages."""
        ...

    @abstractmethod
    async def save_session(
        self,
        session_id: str,
        user_id: str,
        tenant_id: str,
        title: str,
        messages: List[Dict[str, Any]],
    ) -> bool:
        """Upsert chat session and message list."""
        ...

    @abstractmethod
    async def append_message(
        self,
        session_id: str,
        user_id: str,
        tenant_id: str,
        message: Dict[str, Any],
        title: Optional[str] = None,
    ) -> bool:
        """Append an individual message to session and message records."""
        ...

    @abstractmethod
    async def append_turn(
        self,
        session_id: str,
        user_id: str,
        tenant_id: str,
        user_msg: Dict[str, Any],
        assistant_msg: Dict[str, Any],
        title: Optional[str] = None,
    ) -> bool:
        """Atomically append a user query and assistant response turn."""
        ...

    @abstractmethod
    async def list_sessions(
        self,
        user_id: str,
        tenant_id: str,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """List recent chat sessions for a user."""
        ...

    @abstractmethod
    async def delete_session(self, session_id: str, user_id: str, tenant_id: str) -> bool:
        """Remove chat session and history."""
        ...

    @abstractmethod
    async def update_title(self, session_id: str, title: str, user_id: str, tenant_id: str) -> bool:
        """Rename session title."""
        ...

    async def delete_message(self, session_id: str, message_id: str, user_id: str, tenant_id: str) -> bool:
        """Remove an individual message from a session."""
        ...

    async def record_escalation_ticket(self, ticket_data: Dict[str, Any]) -> str:
        """Record unresolved OOD query escalation ticket to MongoDB (RER-RAG-02)."""
        return ""

    async def record_feedback(self, feedback_data: Dict[str, Any]) -> str:
        """Record user feedback and error attribution to MongoDB (EXEC-RAG-04, FR-EXEC-03)."""
        return ""

    async def get_feedbacks(self, tenant_id: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        """Retrieve feedback records for error attribution dashboard reporting."""
        return []


class StoragePort(ABC):
    """Port for Blob / Object Storage (MinIO / S3)."""

    @abstractmethod
    def upload_bytes(
        self,
        bucket: str,
        object_name: str,
        data: bytes,
        content_type: str = "application/octet-stream",
    ) -> str:
        """Store bytes in object storage and return S3 URI."""
        ...

    @abstractmethod
    def download_bytes(self, bucket: str, object_name: str) -> Optional[bytes]:
        """Download raw bytes from object storage."""
        ...

    @abstractmethod
    def delete_object(self, bucket: str, object_name: str) -> bool:
        """Remove file object from storage."""
        ...


class DocumentParserPort(ABC):
    """Port for document file format parsers."""

    @abstractmethod
    def parse(self, file_bytes: bytes, filename: str) -> ParsedDocument:
        """Parse raw file bytes into structured pages and text."""
        ...


class CachePort(ABC):
    """Port for High-Concurrency Multi-Tier Response Caching (FR-EXEC-05 / EXEC-RAG-06)."""

    @abstractmethod
    async def get(
        self,
        query: str,
        tenant_id: str = DEFAULT_TENANT_ID,
        combine_strategy: str = "single_pass_reordered",
        as_of_date: Optional[str] = None,
        user_role: str = "user",
        department: Optional[str] = None,
        similarity_threshold: Optional[float] = None,
    ) -> Optional[Any]:
        """Fetch cached response for query, tenant, strategy, and user_role."""
        ...

    @abstractmethod
    async def set(
        self,
        query: str,
        response: Any,
        tenant_id: str = DEFAULT_TENANT_ID,
        combine_strategy: str = "single_pass_reordered",
        as_of_date: Optional[str] = None,
        ttl_seconds: Optional[int] = None,
        user_role: str = "user",
        department: Optional[str] = None,
        similarity_threshold: Optional[float] = None,
    ) -> bool:
        """Store response in cache with TTL and tenancy/ACL isolation."""
        ...

    @abstractmethod
    async def invalidate_tenant(self, tenant_id: str) -> int:
        """Invalidate all cached responses for a tenant upon document ingestion/deletion."""
        ...

    @abstractmethod
    async def is_healthy(self) -> bool:
        """Check cache liveness and connection health."""
        ...


class NullCacheAdapter(CachePort):
    """
    Null Object implementation of CachePort for test isolation and un-cached environments.
    Guarantees pure Dependency Inversion without forcing Application layers to couple with Infrastructure.
    """

    async def get(
        self,
        query: str,
        tenant_id: str = DEFAULT_TENANT_ID,
        combine_strategy: str = "single_pass_reordered",
        as_of_date: Optional[str] = None,
        user_role: str = "user",
        department: Optional[str] = None,
        similarity_threshold: Optional[float] = None,
    ) -> Optional[Any]:
        return None

    async def set(
        self,
        query: str,
        response: Any,
        tenant_id: str = DEFAULT_TENANT_ID,
        combine_strategy: str = "single_pass_reordered",
        as_of_date: Optional[str] = None,
        ttl_seconds: Optional[int] = None,
        user_role: str = "user",
        department: Optional[str] = None,
        similarity_threshold: Optional[float] = None,
    ) -> bool:
        return True

    async def invalidate_tenant(self, tenant_id: str) -> int:
        return 0

    async def is_healthy(self) -> bool:
        return True


class RerankerPort(ABC):
    """Port for Semantic Cross-Encoder Reranking (FR-RER-01 / RER-RAG-01)."""

    @abstractmethod
    def rerank(
        self,
        query: str,
        candidates: List[CandidateType],
        top_n: int = 5,
        min_threshold: float = 0.75,
    ) -> List[CandidateType]:
        """Score candidate chunks against query and return top_n reranked candidates."""
        ...

    async def arerank(
        self,
        query: str,
        candidates: List[CandidateType],
        top_n: int = 5,
        min_threshold: float = 0.75,
    ) -> List[CandidateType]:
        """
        Non-blocking variant used by the async pipeline. Default runs the synchronous
        implementation in a worker thread so CPU-bound scoring never blocks the event loop;
        network-backed rerankers override this with a native async call.
        """
        return await asyncio.to_thread(
            self.rerank, query=query, candidates=candidates, top_n=top_n, min_threshold=min_threshold
        )


class MessageBrokerPort(ABC):
    """Port for Asynchronous Event/Task Message Broker (RabbitMQ / Kafka)."""

    @abstractmethod
    async def publish(
        self,
        queue_name: str,
        payload: Dict[str, Any],
        max_retries: int = 3,
    ) -> bool:
        """Publish a persistent message to target queue with automatic reconnection & retry."""
        ...

    @abstractmethod
    async def is_healthy(self) -> bool:
        """Check connection liveness to the message broker."""
        ...

    @abstractmethod
    async def close(self) -> None:
        """Gracefully close all connections and channels in pool."""
        ...


class ObservabilityPort(ABC):
    """
    Domain Port for Enterprise RAG Observability, Distributed Tracing, and Telemetry (Masterclass Layer 5).
    Adheres strictly to the Clean Architecture Dependency Inversion Principle.
    """

    @abstractmethod
    def record_request(
        self,
        endpoint: str,
        method: str,
        status_code: int,
        duration: float,
        tenant_id: str = DEFAULT_TENANT_ID,
    ) -> None:
        """Record completed HTTP request duration and status."""
        ...

    @abstractmethod
    def record_stage_latency(
        self,
        stage: str,
        duration: float,
        tenant_id: str = DEFAULT_TENANT_ID,
    ) -> None:
        """
        Record execution duration of individual pipeline stages:
        'rewrite', 'intent', 'retrieval_dense', 'retrieval_sparse',
        'retrieval_hybrid', 'rerank', 'context_assembly', 'llm_ttft', 'llm_generate'.
        """
        ...

    @abstractmethod
    def record_cache_op(
        self,
        cache_type: str,
        result: str,
        tenant_id: str = DEFAULT_TENANT_ID,
    ) -> None:
        """Record cache access: cache_type in {'exact', 'semantic', 'kv_prefix'}, result in {'hit', 'miss', 'set', 'bypass'}."""
        ...

    @abstractmethod
    def record_tokens(
        self,
        model: str,
        token_type: str,
        count: int,
        tenant_id: str = DEFAULT_TENANT_ID,
    ) -> None:
        """Record token consumption: token_type in {'prompt', 'completion', 'cached_prefix'}."""
        ...

    @abstractmethod
    def record_retrieval(
        self,
        retriever_type: str,
        chunk_count: int,
        tenant_id: str = DEFAULT_TENANT_ID,
    ) -> None:
        """Record number of retrieved candidate chunks."""
        ...

    @abstractmethod
    def record_groundedness(
        self,
        score: float,
        tenant_id: str = DEFAULT_TENANT_ID,
    ) -> None:
        """Record anti-hallucination / groundedness score [0.0, 1.0]."""
        ...

    @abstractmethod
    def record_error(
        self,
        error_type: str,
        stage: str,
        tenant_id: str = DEFAULT_TENANT_ID,
    ) -> None:
        """Record pipeline error occurrence."""
        ...

    @abstractmethod
    def record_ingestion(
        self,
        tenant_id: str,
        status: str,
        duration: float,
        chunk_count: int,
        file_type: str = "unknown",
    ) -> None:
        """Record document ingestion metrics."""
        ...


class NullObservabilityAdapter(ObservabilityPort):
    """No-op Observability Adapter for isolated testing without Prometheus dependencies."""

    def record_request(
        self,
        endpoint: str,
        method: str,
        status_code: int,
        duration: float,
        tenant_id: str = DEFAULT_TENANT_ID,
    ) -> None:
        pass

    def record_stage_latency(
        self,
        stage: str,
        duration: float,
        tenant_id: str = DEFAULT_TENANT_ID,
    ) -> None:
        pass

    def record_cache_op(
        self,
        cache_type: str,
        result: str,
        tenant_id: str = DEFAULT_TENANT_ID,
    ) -> None:
        pass

    def record_tokens(
        self,
        model: str,
        token_type: str,
        count: int,
        tenant_id: str = DEFAULT_TENANT_ID,
    ) -> None:
        pass

    def record_retrieval(
        self,
        retriever_type: str,
        chunk_count: int,
        tenant_id: str = DEFAULT_TENANT_ID,
    ) -> None:
        pass

    def record_groundedness(
        self,
        score: float,
        tenant_id: str = DEFAULT_TENANT_ID,
    ) -> None:
        pass

    def record_error(
        self,
        error_type: str,
        stage: str,
        tenant_id: str = DEFAULT_TENANT_ID,
    ) -> None:
        pass

    def record_ingestion(
        self,
        tenant_id: str,
        status: str,
        duration: float,
        chunk_count: int,
        file_type: str = "unknown",
    ) -> None:
        pass


