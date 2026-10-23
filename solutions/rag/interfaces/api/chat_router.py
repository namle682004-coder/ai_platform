"""
FastAPI REST Router for Enterprise RAG Chat & Session Persistence.
Thin interface controller delegating directly to Application Use Cases.
"""

import hmac
import logging
import os
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, File, Header, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from .identity import extract_role, extract_tenant, extract_user, is_admin
from .rate_limiter import RateLimitDependency

from ...application.dtos import (
    ChatSessionDTO,
    FeedbackRequestDTO,
    FeedbackResponseDTO,
    RagChatRequestDTO,
    RagChatResponseDTO,
    SessionListResponseDTO,
)
from ...application.use_cases.chat_use_case import INFRASTRUCTURE_ERRORS, RagChatUseCase
from ...application.use_cases.session_use_case import RagSessionUseCase
from ...infrastructure.adapters.embedding_adapter import HttpEmbeddingAdapter
from ...infrastructure.adapters.llm_adapter import HttpLlmAdapter
from ...infrastructure.adapters.qdrant_adapter import QdrantVectorStoreAdapter
from ...infrastructure.parsers.factory import parser_factory
from ...infrastructure.repositories.mongo_session_repo import MongoSessionRepositoryAdapter
from ...application.components.error_attribution import error_attribution_service

logger = logging.getLogger("aip-rag.api.chat")

router = APIRouter(prefix="/v1/rag", tags=["Knowledge & RAG"])

_chat_limiter = RateLimitDependency(requests_per_minute=3000)
_adhoc_limiter = RateLimitDependency(requests_per_minute=600)

from ...config import rag_settings

# Dependency injection for default container
from ...infrastructure.adapters.redis_cache_adapter import redis_cache
from ...infrastructure.adapters.reranker_adapter import build_reranker
from ...infrastructure.observability import rag_observability

# Model endpoints (embed-standard / rerank-standard / chat aliases) resolve through the alias registry.
_vector_store = QdrantVectorStoreAdapter(base_url=rag_settings.qdrant_url, collection_name=rag_settings.collection_name)
_embedding_service = HttpEmbeddingAdapter(dim=rag_settings.embedding_dim)
_llm_service = HttpLlmAdapter()
_reranker_service = build_reranker()
_session_repo = MongoSessionRepositoryAdapter(mongo_uri=rag_settings.mongo_uri)

chat_use_case = RagChatUseCase(
    vector_store=_vector_store,
    embedding_service=_embedding_service,
    llm_service=_llm_service,
    session_repo=_session_repo,
    cache_service=redis_cache,
    reranker_service=_reranker_service,
    observability_service=rag_observability,
)

session_use_case = RagSessionUseCase(session_repo=_session_repo)


_extract_tenant = extract_tenant
_extract_user = extract_user
_extract_role = extract_role


@router.post("/adhoc/parse", dependencies=[Depends(_adhoc_limiter)])
async def parse_adhoc_document(
    file: UploadFile = File(...),
    request: Request = None,
) -> Dict[str, Any]:
    """Parse temporary attached document directly in RAM (Ad-hoc RAG).
    Extracts text without uploading to MinIO and without indexing vectors into Qdrant.
    """
    try:
        file_bytes = await file.read()
        filename = file.filename or "tep_dinh_kem"
        parsed_doc = parser_factory.parse(file_bytes, filename)
        full_text = chr(10).join(p.text for p in parsed_doc.pages if p.text)

        return {
            "filename": filename,
            "file_type": parsed_doc.file_type,
            "total_pages": len(parsed_doc.pages),
            "size_bytes": len(file_bytes),
            "text": full_text,
            "excerpt": full_text[:300].strip() + "..." if len(full_text) > 300 else full_text,
        }
    except Exception as e:
        logger.error(f"Failed to parse ad-hoc document: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Không thể đọc file đính kèm: {str(e)}"
        ) from e


@router.post("/chat", response_model=RagChatResponseDTO, dependencies=[Depends(_chat_limiter)])
async def chat_rag(
    payload: RagChatRequestDTO,
    request: Request,
    authorization: Optional[str] = Header(None),
) -> Any:
    """Enterprise RAG QA endpoint with hybrid search, grounding guardrail, and citations."""
    tenant_id = _extract_tenant(request)
    user_id = _extract_user(request)
    user_role = _extract_role(request)

    if payload.stream:
        return StreamingResponse(
            chat_use_case.stream_execute(
                request=payload,
                tenant_id=tenant_id,
                user_id=user_id,
                user_role=user_role,
                authorization=authorization,
            ),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    try:
        return await chat_use_case.execute(
            request=payload,
            tenant_id=tenant_id,
            user_id=user_id,
            user_role=user_role,
            authorization=authorization,
        )
    except INFRASTRUCTURE_ERRORS as exc:
        # An outage must not be reported as "no relevant documents" (and must not open an escalation ticket).
        logger.error("RAG chat failed on infrastructure dependency: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": type(exc).__name__, "message": "Dịch vụ tạm thời gián đoạn, vui lòng thử lại sau."},
            headers={"Retry-After": "5"},
        ) from exc


@router.post("/chat/stream", dependencies=[Depends(_chat_limiter)])
async def chat_rag_stream(
    payload: RagChatRequestDTO,
    request: Request,
    authorization: Optional[str] = Header(None),
) -> StreamingResponse:
    """Dedicated Real-Time SSE Streaming API endpoint (EXEC-RAG-05 / FR-EXEC-02)."""
    payload.stream = True
    tenant_id = _extract_tenant(request)
    user_id = _extract_user(request)
    user_role = _extract_role(request)

    return StreamingResponse(
        chat_use_case.stream_execute(
            request=payload,
            tenant_id=tenant_id,
            user_id=user_id,
            user_role=user_role,
            authorization=authorization,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/sessions", response_model=SessionListResponseDTO)
async def list_rag_sessions(
    request: Request,
    limit: int = Query(default=50, ge=1, le=100),
) -> SessionListResponseDTO:
    """Retrieve recent chat sessions for the authenticated user."""
    tenant_id = _extract_tenant(request)
    user_id = _extract_user(request)
    return await session_use_case.list_sessions(user_id=user_id, tenant_id=tenant_id, limit=limit)


@router.get("/sessions/{session_id}", response_model=ChatSessionDTO)
async def get_rag_session(
    session_id: str,
    request: Request,
) -> ChatSessionDTO:
    """Retrieve a single chat session with its full message history and citations."""
    tenant_id = _extract_tenant(request)
    user_id = _extract_user(request)
    sess = await session_use_case.get_session(session_id=session_id, user_id=user_id, tenant_id=tenant_id)
    if not sess:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat session not found")
    return sess


class UpdateSessionTitleRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=100)


@router.patch("/sessions/{session_id}")
async def rename_rag_session(
    session_id: str,
    payload: UpdateSessionTitleRequest,
    request: Request,
) -> Dict[str, Any]:
    """Rename a conversation title."""
    tenant_id = _extract_tenant(request)
    user_id = _extract_user(request)
    ok = await session_use_case.rename_session(session_id=session_id, title=payload.title, user_id=user_id, tenant_id=tenant_id)
    return {"status": "success" if ok else "failed", "session_id": session_id, "title": payload.title}


@router.delete("/sessions/{session_id}")
async def delete_rag_session(
    session_id: str,
    request: Request,
) -> Dict[str, Any]:
    """Delete a conversation session permanently."""
    tenant_id = _extract_tenant(request)
    user_id = _extract_user(request)
    ok = await session_use_case.delete_session(session_id=session_id, user_id=user_id, tenant_id=tenant_id)
    return {"status": "deleted" if ok else "not_found", "session_id": session_id}


@router.delete("/sessions/{session_id}/messages/{message_id}")
async def delete_rag_message(
    session_id: str,
    message_id: str,
    request: Request,
) -> Dict[str, Any]:
    """Delete a specific message from a conversation session."""
    tenant_id = _extract_tenant(request)
    user_id = _extract_user(request)
    ok = await session_use_case.delete_message(
        session_id=session_id,
        message_id=message_id,
        user_id=user_id,
        tenant_id=tenant_id,
    )
    return {"status": "deleted" if ok else "not_found", "session_id": session_id, "message_id": message_id}


@router.post("/feedback", response_model=FeedbackResponseDTO, status_code=status.HTTP_200_OK)
async def record_rag_feedback(
    payload: FeedbackRequestDTO,
    request: Request,
) -> FeedbackResponseDTO:
    """
    User Feedback & 5-Stage Error Attribution Logging API (EXEC-RAG-04, EXEC-RAG-05, FR-EXEC-03).
    Classifies root causes into: PRE_RETRIEVAL_ERROR, RETRIEVAL_MISS, RERANKER_DROP, LLM_SYNTHESIS_ERROR, OOD_HALLUCINATION.
    """
    import uuid
    tenant_id = _extract_tenant(request)
    user_id = _extract_user(request)
    feedback_id = f"fb_rec_{uuid.uuid4().hex[:8]}"

    # Determine whether feedback is negative or explicitly categorized
    is_negative = str(payload.rating).lower() in ("dislike", "-1", "negative", "0") or bool(payload.error_category)
    attribution_result = None
    if is_negative:
        attribution_result = error_attribution_service.attribute(
            query=payload.query or "",
            answer=payload.response_text or "",
            rating=payload.rating,
            user_feedback=payload.feedback_text or payload.comments,
            error_category=payload.error_category,
        )

    feedback_record = {
        "feedback_id": feedback_id,
        "trace_id": payload.trace_id,
        "session_id": payload.session_id,
        "tenant_id": tenant_id,
        "user_id": user_id,
        "query": payload.query,
        "response_text": payload.response_text,
        "rating": payload.rating,
        "feedback_text": payload.feedback_text or payload.comments,
        "error_category": payload.error_category,
        "cited_doc_ids": payload.cited_doc_ids,
        "attributed_stage": attribution_result.stage.value if attribution_result else None,
        "attribution_details": attribution_result.model_dump() if attribution_result else None,
    }

    await _session_repo.record_feedback(feedback_record)
    logger.info(
        "Recorded feedback %s for trace_id=%s rating=%s (attributed_stage=%s)",
        feedback_id,
        payload.trace_id,
        payload.rating,
        attribution_result.stage.value if attribution_result else "N/A",
    )

    return FeedbackResponseDTO(
        status="recorded",
        feedback_id=feedback_id,
        attributed_stage=attribution_result.stage.value if attribution_result else None,
        details=attribution_result.model_dump() if attribution_result else None,
    )


@router.get("/feedback/dashboard")
async def get_feedback_dashboard(
    request: Request,
    limit: int = Query(default=200, ge=1, le=1000),
) -> Dict[str, Any]:
    """Executive 5-Stage Error Attribution Dashboard & Funnel Analysis (EXEC-RAG-04)."""
    tenant_id = _extract_tenant(request)
    records = await _session_repo.get_feedbacks(tenant_id=tenant_id, limit=limit)
    return error_attribution_service.generate_executive_dashboard(records)


@router.post("/cache/clear", status_code=status.HTTP_200_OK)
async def clear_cache(
    request: Request,
    scope: str = Query(default="tenant", pattern="^(tenant|all)$"),
) -> Dict[str, Any]:
    """
    Manually invalidate query cache (tenant-level or cluster-wide) for hot updates (FR-EXEC-05, EXEC-RAG-06).
    Restricted to authorized users: cluster-wide 'all' scope strictly requires admin role or API key.
    """
    api_key = request.headers.get("X-API-Key") or request.headers.get("Authorization", "")
    api_key = api_key[7:] if api_key.startswith("Bearer ") else api_key
    admin_key = getattr(rag_settings, "admin_api_key", None) or os.getenv("AIP_ADMIN_API_KEY", "")
    has_admin_key = bool(admin_key) and hmac.compare_digest(api_key, admin_key)

    if scope == "all" and not (is_admin(request) or has_admin_key):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cluster-wide cache clearing requires admin role or valid admin credentials.",
        )

    from ...infrastructure.adapters.redis_cache_adapter import redis_cache
    if scope == "all":
        await redis_cache.invalidate_all()
        return {"status": "cleared", "scope": "all"}
    tenant_id = _extract_tenant(request)
    await redis_cache.invalidate_tenant(tenant_id)
    return {"status": "cleared", "scope": "tenant", "tenant_id": tenant_id}

