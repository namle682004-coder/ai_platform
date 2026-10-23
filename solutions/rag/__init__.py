"""
AIP Enterprise RAG Solution.
Engineered following Domain-Driven Design (DDD) principles:
- domain: entities, ports, exceptions
- application: use cases, DTOs, domain components
- infrastructure: concrete adapters, repositories, parsers
- interfaces: FastAPI routers, RabbitMQ worker consumer
"""

from .application.use_cases import (
    DocumentIngestionUseCase,
    KnowledgeManagementUseCase,
    RagChatUseCase,
    RagSessionUseCase,
)
from .config import rag_settings
from .domain.entities import (
    ChatMessage,
    ChatRole,
    ChatSession,
    Citation,
    Document,
    DocumentChunk,
    DocumentStatus,
    EffectiveStatus,
    QueryIntent,
)
try:
    from .interfaces.api.router import rag_api_router
except Exception:
    rag_api_router = None

try:
    from .interfaces.worker.consumer import RagWorkerConsumer
except Exception:
    RagWorkerConsumer = None

__all__ = [
    "rag_settings",
    "rag_api_router",
    "RagWorkerConsumer",
    "RagChatUseCase",
    "RagSessionUseCase",
    "DocumentIngestionUseCase",
    "KnowledgeManagementUseCase",
    "ChatSession",
    "ChatMessage",
    "Citation",
    "ChatRole",
    "Document",
    "DocumentChunk",
    "DocumentStatus",
    "EffectiveStatus",
    "QueryIntent",
]
