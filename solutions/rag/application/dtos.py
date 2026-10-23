"""
Data Transfer Objects (DTOs) for AIP Enterprise RAG Solution.
Strict validation schemas for REST APIs, use cases, and worker messages.
"""

import time
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field, field_validator

from ..domain.entities import normalize_iso_date

CONFIDENCE_GATE_MIN_THRESHOLD = 0.75
DEFAULT_CONFIDENCE_THRESHOLD = CONFIDENCE_GATE_MIN_THRESHOLD


class RagCitationDTO(BaseModel):
    index: int
    doc_id: str
    title: str
    page_number: int
    score: float
    excerpt: str
    document_name: Optional[str] = None
    page: Optional[int] = None
    section: Optional[str] = None
    relevance_score: Optional[float] = None
    quote: Optional[str] = None


class RagChatRequestDTO(BaseModel):
    query: str = Field(..., min_length=2, description="User question to answer against knowledge base")
    conversation_id: Optional[str] = Field(None, description="Optional conversation session ID")
    history: Optional[List[Dict[str, str]]] = Field(
        None,
        description="Previous conversation turns for multi-turn context (e.g. [{\"role\": \"user\", \"content\": \"...\"}])",
    )
    model: str = Field(default="chat-general-standard", description="Model alias for LLM reasoning")
    department: Optional[str] = Field(None, description="Filter documents by department")
    doc_ids: Optional[List[str]] = Field(None, description="Restrict search to specific document IDs")
    similarity_threshold: float = Field(
        default=DEFAULT_CONFIDENCE_THRESHOLD,
        ge=0.0,
        le=1.0,
        description="Minimum cosine similarity score required; queries below this will be rejected to prevent hallucination",
    )
    top_k: int = Field(default=4, ge=1, le=20, description="Number of context chunks to retrieve")
    temperature: float = Field(default=0.2, ge=0.0, le=1.0, description="Low temperature for factual accuracy")
    max_tokens: int = Field(default=1024, ge=64, le=4096)
    stream: bool = Field(default=False, description="Whether to stream response tokens via Server-Sent Events (SSE)")
    include_shared_scope: bool = Field(default=False, description="Whether to include shared enterprise knowledge in search scope")
    combine_strategy: Optional[Literal["stuff", "map_reduce", "refine", "map_rerank", "auto"]] = Field(
        default="auto",
        description="Context combine strategy: 'stuff', 'map_reduce', 'refine', 'map_rerank', or 'auto' (Slide 80 standard)",
    )
    adhoc_context: Optional[str] = Field(None, description="Optional text context parsed in-memory from user attached file")
    adhoc_filename: Optional[str] = Field(None, description="Optional filename of user attached file")
    enable_hyde: Optional[bool] = Field(
        default=None,
        description="Whether to enable Hypothetical Document Embeddings (HyDE - Slide 138). None for auto-trigger on short/definitional queries, True to force enable, False to disable.",
    )
    multi_hop: Optional[bool] = Field(
        default=None,
        description="Whether to enable Multi-Hop Reasoning & Iterative RAG (Slide 94–103). None for auto-trigger on comparative/multi-step questions, True to force enable, False to disable.",
    )
    as_of_date: Optional[str] = Field(
        default=None,
        description="Optional YYYY-MM-DD date to filter legally active documents as of this date (FR-RET-06)",
    )

    @field_validator("as_of_date", mode="before")
    @classmethod
    def _normalize_as_of_date(cls, value: Any) -> Optional[str]:
        return normalize_iso_date(value)


class ClarificationDTO(BaseModel):
    question: str
    options: List[str]
    intent_context: str


class RagChatResponseDTO(BaseModel):
    answer: str
    model: str
    citations: List[RagCitationDTO]
    latency_ms: float
    intent: str = "QA"
    combine_strategy: Optional[str] = "stuff"
    session_id: Optional[str] = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    pre_retrieval_tier: Optional[str] = "TIER_1_HEURISTIC"
    pre_retrieval_latency_ms: Optional[float] = 0.0
    ttft_ms: Optional[float] = None
    hyde_active: Optional[bool] = False
    hypothetical_doc: Optional[str] = None
    hyde_latency_ms: Optional[float] = 0.0
    is_multi_hop: Optional[bool] = False
    sub_queries: Optional[List[str]] = None
    hops_executed: Optional[int] = 1
    circuit_breaker_triggered: Optional[bool] = False
    is_refusal: Optional[bool] = False
    status: Optional[str] = "success"
    escalation: Optional[Dict[str, Any]] = None
    clarification: Optional[ClarificationDTO] = None
    cache_hit: Optional[bool] = False
    telemetry: Optional[Dict[str, Any]] = None


import uuid


class ChatMessageDTO(BaseModel):
    message_id: str = Field(default_factory=lambda: f"msg_{uuid.uuid4().hex[:12]}")
    role: str
    content: str
    timestamp: float = Field(default_factory=time.time)
    citations: List[RagCitationDTO] = Field(default_factory=list)
    model: Optional[str] = None
    intent: Optional[str] = None
    tokens: Optional[int] = None
    latency_ms: Optional[float] = None


class ChatSessionDTO(BaseModel):
    session_id: str
    user_id: str
    tenant_id: str
    title: str
    messages: List[ChatMessageDTO]
    created_at: float
    updated_at: float
    message_count: int = 0


class SessionListItemDTO(BaseModel):
    session_id: str
    title: str
    last_message: Optional[str] = None
    updated_at: float
    message_count: int = 0


class SessionListResponseDTO(BaseModel):
    items: List[SessionListItemDTO]
    total: int


class DocumentResponseDTO(BaseModel):
    doc_id: str
    tenant_id: str
    title: str
    filename: str
    file_type: str
    file_size_bytes: int
    status: str
    total_chunks: int
    department: Optional[str] = None
    allowed_roles: List[str] = Field(default_factory=lambda: ["*"])
    created_at: str
    updated_at: str
    s3_uri: Optional[str] = None
    effective_status: Optional[str] = "ACTIVE"
    effective_date: Optional[str] = None
    expiry_date: Optional[str] = None


class DocumentListResponseDTO(BaseModel):
    items: List[DocumentResponseDTO]
    total: int
    page: int
    page_size: int


class FeedbackRequestDTO(BaseModel):
    trace_id: Optional[str] = None
    session_id: Optional[str] = None
    query: Optional[str] = None
    response_text: Optional[str] = None
    rating: Any = Field(..., description="1 / -1 for numeric rating, or 'like' / 'dislike'")
    comments: Optional[str] = None
    feedback_text: Optional[str] = None
    error_category: Optional[str] = None
    cited_doc_ids: List[str] = Field(default_factory=list)


class FeedbackResponseDTO(BaseModel):
    status: str = "recorded"
    feedback_id: str
    attributed_stage: Optional[str] = None
    details: Optional[Dict[str, Any]] = None


class QACreateRequestDTO(BaseModel):
    question: str = Field(..., min_length=2, description="FAQ Question / Prompt")
    answer: str = Field(..., min_length=2, description="Approved official answer")
    question_variations: List[str] = Field(default_factory=list, description="Paraphrased question variants for broader recall (BRD 3.4)")
    category: Optional[str] = Field(default="general", description="FAQ Category or module")
    tags: List[str] = Field(default_factory=list, description="Associated tags")
    allowed_roles: List[str] = Field(default_factory=lambda: ["*"], description="Role ACLs")
    effective_status: Optional[str] = Field(default="ACTIVE", description="Regulatory/business status (ACTIVE, EXPIRED, DRAFT)")
    effective_date: Optional[str] = Field(default=None, description="Effective from ISO date (e.g. 2024-01-01)")
    expiry_date: Optional[str] = Field(default=None, description="Expiry ISO date (e.g. 2025-12-31)")

    @field_validator("effective_date", "expiry_date", mode="before")
    @classmethod
    def _normalize_dates(cls, value: Any) -> Optional[str]:
        return normalize_iso_date(value)


class QACreateResponseDTO(BaseModel):
    status: str = "indexed"
    qa_id: str
    indexing_latency_ms: float
    qdrant_point_id: str


class QADeleteResponseDTO(BaseModel):
    status: str = "deleted"
    qa_id: str

