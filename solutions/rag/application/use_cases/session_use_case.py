"""
Enterprise RAG Chat Session Management Use Case.
Handles session listing, history retrieval, session renaming, and deletion.
"""

import logging
from typing import Optional

from ...domain.ports import SessionRepositoryPort
from ..dtos import (
    ChatMessageDTO,
    ChatSessionDTO,
    RagCitationDTO,
    SessionListItemDTO,
    SessionListResponseDTO,
)

logger = logging.getLogger("aip-rag.session_use_case")


class RagSessionUseCase:
    """Use case for persistent chat sessions."""

    def __init__(self, session_repo: SessionRepositoryPort) -> None:
        self.session_repo = session_repo

    async def list_sessions(
        self,
        user_id: str,
        tenant_id: str,
        limit: int = 50,
    ) -> SessionListResponseDTO:
        raw_items = await self.session_repo.list_sessions(user_id, tenant_id, limit=limit)
        items = []
        for item in raw_items:
            items.append(
                SessionListItemDTO(
                    session_id=item["session_id"],
                    title=item.get("title", "New Conversation"),
                    last_message=item.get("last_message"),
                    updated_at=float(item.get("updated_at", 0.0)),
                    message_count=int(item.get("message_count", 0)),
                )
            )
        return SessionListResponseDTO(items=items, total=len(items))

    async def get_session(
        self,
        session_id: str,
        user_id: str,
        tenant_id: str,
    ) -> Optional[ChatSessionDTO]:
        record = await self.session_repo.get_session(session_id, user_id, tenant_id)
        if not record:
            return None

        messages = []
        for m in record.get("messages", []):
            citations = [
                RagCitationDTO(
                    index=c.get("index", idx + 1),
                    doc_id=c.get("doc_id", ""),
                    title=c.get("title", ""),
                    page_number=c.get("page_number", 1),
                    score=float(c.get("score", 0.0)),
                    excerpt=c.get("excerpt", ""),
                )
                for idx, c in enumerate(m.get("citations", []))
            ]
            messages.append(
                ChatMessageDTO(
                    message_id=m.get("message_id"),
                    role=m.get("role", "user"),
                    content=m.get("content", ""),
                    timestamp=float(m.get("timestamp", 0.0)),
                    citations=citations,
                    model=m.get("model"),
                    intent=m.get("intent"),
                    prompt_tokens=m.get("prompt_tokens"),
                    completion_tokens=m.get("completion_tokens"),
                    latency_ms=m.get("latency_ms"),
                )
            )

        return ChatSessionDTO(
            session_id=record["session_id"],
            user_id=record.get("user_id", user_id),
            tenant_id=record.get("tenant_id", tenant_id),
            title=record.get("title", "Conversation"),
            messages=messages,
            message_count=int(record.get("message_count", len(messages))),
            created_at=float(record.get("created_at", 0.0)),
            updated_at=float(record.get("updated_at", 0.0)),
        )

    async def rename_session(
        self,
        session_id: str,
        title: str,
        user_id: str,
        tenant_id: str,
    ) -> bool:
        return await self.session_repo.update_title(session_id, title, user_id, tenant_id)

    async def delete_session(
        self,
        session_id: str,
        user_id: str,
        tenant_id: str,
    ) -> bool:
        return await self.session_repo.delete_session(session_id, user_id, tenant_id)

    async def delete_message(
        self,
        session_id: str,
        message_id: str,
        user_id: str,
        tenant_id: str,
    ) -> bool:
        if hasattr(self.session_repo, "delete_message"):
            return await self.session_repo.delete_message(session_id, message_id, user_id, tenant_id)
        return False
