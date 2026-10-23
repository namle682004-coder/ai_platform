"""
Gateway RAG Chat & Session Persistence Router.
Forwarding router delegating cleanly to Enterprise RAG Solution (DDD Architecture).
"""

from solutions.rag.interfaces.api.chat_router import (
    chat_rag,
    chat_use_case,
    delete_rag_session,
    get_rag_session,
    list_rag_sessions,
    rename_rag_session,
    router,
    session_use_case,
)

__all__ = [
    "router",
    "chat_use_case",
    "session_use_case",
    "chat_rag",
    "list_rag_sessions",
    "get_rag_session",
    "rename_rag_session",
    "delete_rag_session",
]
