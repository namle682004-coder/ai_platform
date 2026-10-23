"""
Domain Entities and Value Objects for AIP Enterprise RAG Solution.
Core business models decoupled from infrastructure, framework, and database layers.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Any, Dict, List, Optional

DEFAULT_TENANT_ID: str = "proj_default"
FALLBACK_TENANT_ALIASES = frozenset({"default_tenant", "tenant_default", "default", "global", ""})


def normalize_tenant_id(tenant_id: Optional[str]) -> str:
    """
    Canonical normalization for Multi-Tenant isolation (NFR-6.1).
    Maps legacy/default aliases ('default_tenant', 'tenant_default', 'default', 'global', empty)
    consistently to the canonical DEFAULT_TENANT_ID ('proj_default').
    """
    if not tenant_id:
        return DEFAULT_TENANT_ID
    cleaned = str(tenant_id).strip()
    if "," in cleaned:
        cleaned = cleaned.split(",")[0].strip()
    if cleaned.lower() in FALLBACK_TENANT_ALIASES:
        return DEFAULT_TENANT_ID
    return cleaned


_DMY_RE = re.compile(r"^(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})$")
_YMD_RE = re.compile(r"^(\d{4})[/.-](\d{1,2})[/.-](\d{1,2})(?:[T ].*)?$")


def normalize_iso_date(value: Optional[Any]) -> Optional[str]:
    """
    Normalise a document validity date to ISO `YYYY-MM-DD`.

    Vietnamese documents use DD/MM/YYYY. Qdrant range filters only understand ISO dates,
    and an unparseable value makes a `must_not` expiry condition silently pass, so an
    expired document would be served as current. Returns None for empty input and raises
    ValueError for anything that is not a valid calendar date.
    """
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    m = _DMY_RE.match(raw)
    if m:
        day, month, year = (int(g) for g in m.groups())
    else:
        m = _YMD_RE.match(raw)
        if not m:
            raise ValueError(f"Unrecognised date '{raw}' (expected DD/MM/YYYY or YYYY-MM-DD)")
        year, month, day = (int(g) for g in m.groups())
    return date(year, month, day).isoformat()


class ChatRole(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


class DocumentStatus(str, Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    INDEXED = "INDEXED"
    FAILED = "FAILED"


class EffectiveStatus(str, Enum):
    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"
    DRAFT = "DRAFT"
    ARCHIVED = "ARCHIVED"
    DEPRECATED = "DEPRECATED"
    SUPERSEDED = "SUPERSEDED"
    CANCELLED = "CANCELLED"


class QueryIntent(str, Enum):
    QA = "QA"
    HOWTO_TROUBLESHOOTING = "HOWTO_TROUBLESHOOTING"
    COMPARATIVE = "COMPARATIVE"
    MULTI_TURN_FOLLOWUP = "MULTI_TURN_FOLLOWUP"
    OUT_OF_DOMAIN = "OUT_OF_DOMAIN"
    CHITCHAT = "CHITCHAT"
    REFUSAL = "REFUSAL"
    AMBIGUOUS_SYMPTOM = "AMBIGUOUS_SYMPTOM"


@dataclass
class Citation:
    index: int
    doc_id: str
    title: str
    page_number: int
    score: float
    excerpt: str


@dataclass
class ChatMessage:
    message_id: str
    role: ChatRole
    content: str
    timestamp: float = field(default_factory=time.time)
    citations: List[Citation] = field(default_factory=list)
    model: Optional[str] = None
    intent: Optional[str] = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: float = 0.0


@dataclass
class ChatSession:
    session_id: str
    user_id: str
    tenant_id: str
    title: str
    messages: List[ChatMessage] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    message_count: int = 0

    def add_message(
        self,
        message_id: str,
        role: ChatRole,
        content: str,
        citations: Optional[List[Citation]] = None,
        model: Optional[str] = None,
        intent: Optional[str] = None,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        latency_ms: float = 0.0,
    ) -> ChatMessage:
        msg = ChatMessage(
            message_id=message_id,
            role=role,
            content=content,
            citations=citations or [],
            model=model,
            intent=intent,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            latency_ms=latency_ms,
        )
        self.messages.append(msg)
        self.message_count = len(self.messages)
        self.updated_at = time.time()
        return msg


@dataclass
class DocumentChunk:
    doc_id: str
    chunk_index: int
    page_number: int
    text: str
    chunk_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.chunk_id:
            self.chunk_id = f"{self.doc_id}_{self.chunk_index}"


@dataclass
class ParsedPage:
    page_number: int
    text: str


@dataclass
class ParsedDocument:
    filename: str
    file_type: str
    pages: List[ParsedPage] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def full_text(self) -> str:
        return "\n\n".join(p.text for p in self.pages if p.text.strip())


@dataclass
class RetrievalCandidate:
    doc_id: str
    chunk_id: str
    title: str
    filename: str
    page_number: int
    text: str
    score: float
    department: Optional[str] = None
    allowed_roles: List[str] = field(default_factory=lambda: ["*"])
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Document:
    doc_id: str
    tenant_id: str
    title: str
    filename: str
    file_type: str
    file_size_bytes: int
    status: DocumentStatus
    total_chunks: int = 0
    total_pages: int = 0
    department: Optional[str] = None
    allowed_roles: List[str] = field(default_factory=lambda: ["*"])
    s3_bucket: Optional[str] = None
    s3_object_name: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    error_message: Optional[str] = None
