"""
FastAPI REST Router for Enterprise RAG Chat & Session Persistence.
Thin interface controller delegating directly to Application Use Cases.
"""

import asyncio
import hmac
import logging
import os
import time
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, File, Header, HTTPException, Query, Request, Response, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from .identity import extract_role, extract_tenant, extract_user, is_admin, is_support
from .rate_limiter import ChatRateLimitDependency, RateLimitDependency

from ...application.dtos import (
    ChatSessionDTO,
    FeedbackRequestDTO,
    FeedbackResponseDTO,
    RagChatRequestDTO,
    RagChatResponseDTO,
    SessionListResponseDTO,
)
from ...application.components import media_assets
from ...application.use_cases.chat_use_case import INFRASTRUCTURE_ERRORS, RagChatUseCase, media_secret, unavailable_reply
from ...infrastructure.adapters.storage_adapter import MinioStorageAdapter
from ...application.use_cases.session_use_case import RagSessionUseCase
from ...infrastructure.adapters.embedding_adapter import HttpEmbeddingAdapter
from ...infrastructure.adapters.llm_adapter import HttpLlmAdapter
from ...infrastructure.adapters.qdrant_adapter import QdrantVectorStoreAdapter
from ...infrastructure.parsers.factory import parser_factory
from ...infrastructure.repositories.mongo_session_repo import MongoSessionRepositoryAdapter
from ...infrastructure.repositories.mongo_support_repo import MongoSupportRepository
from ...application.components.error_attribution import error_attribution_service
from ...application.components.run_trace import chunk_ref
from ...application.components.trace_diagnosis import diagnose, final_route

logger = logging.getLogger("aip-rag.api.chat")

router = APIRouter(prefix="/v1/rag", tags=["Knowledge & RAG"])

_chat_limiter = ChatRateLimitDependency()
_adhoc_limiter = RateLimitDependency(requests_per_minute=600)

from ...config import rag_settings

# Dependency injection for default container
from ...infrastructure.adapters.redis_cache_adapter import redis_cache
from ...infrastructure.adapters.reranker_adapter import build_reranker
from ...infrastructure.observability import RagTracer, rag_observability
from ...infrastructure.repositories.mongo_table_repo import MongoTableStore
from ...infrastructure.repositories.mongo_trace_store import MongoTraceStore

# Model endpoints (embed-standard / rerank-standard / chat aliases) resolve through the alias registry.
_vector_store = QdrantVectorStoreAdapter(base_url=rag_settings.qdrant_url, collection_name=rag_settings.collection_name)
_embedding_service = HttpEmbeddingAdapter(dim=rag_settings.embedding_dim)
_llm_service = HttpLlmAdapter()
_reranker_service = build_reranker()
_session_repo = MongoSessionRepositoryAdapter(mongo_uri=rag_settings.mongo_uri)
_trace_store = MongoTraceStore(mongo_uri=rag_settings.mongo_uri, retention_days=rag_settings.trace_retention_days)

chat_use_case = RagChatUseCase(
    vector_store=_vector_store,
    embedding_service=_embedding_service,
    llm_service=_llm_service,
    session_repo=_session_repo,
    cache_service=redis_cache,
    reranker_service=_reranker_service,
    observability_service=rag_observability,
    trace_store=_trace_store,
    table_store=MongoTableStore(rag_settings.mongo_uri),
    support_repo=MongoSupportRepository(rag_settings.mongo_uri),
)


_media_limiter = RateLimitDependency(requests_per_minute=3000)
_media_storage = MinioStorageAdapter(
    endpoint=rag_settings.minio_endpoint,
    access_key=rag_settings.minio_root_user,
    secret_key=rag_settings.minio_root_password,
)


@router.get("/media/{doc_id}/{filename}", dependencies=[Depends(_media_limiter)], include_in_schema=False)
async def get_document_image(
    doc_id: str,
    filename: str,
    t: str = Query("", description="tenant of the document"),
    s: str = Query("", description="signature"),
    e: int = Query(0, description="expiry (unix seconds, 0 = none)"),
) -> Response:
    """
    An image of an indexed document, by signed URL (the answers carry them). A browser <img> request has
    no identity headers, so the signature is the authorization: it binds tenant, document and file.
    """
    if not (rag_settings.media_enabled and media_assets.valid_ref(doc_id, filename)):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    if not media_assets.verify(media_secret(), t, doc_id, filename, s, e):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid or expired image link")
    bucket = rag_settings.media_bucket or rag_settings.minio_bucket
    data = await asyncio.to_thread(_media_storage.download_bytes, bucket, media_assets.object_key(t, doc_id, filename))
    if not data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return Response(
        content=data,
        media_type=media_assets.content_type(filename),
        headers={
            # Files are named by content hash: the bytes behind a URL never change.
            "Cache-Control": "private, max-age=86400, immutable",
            "X-Content-Type-Options": "nosniff",
            "Content-Disposition": f"inline; filename={filename}",
        },
    )


def _request_trace_id() -> Optional[str]:
    """The trace id the observability middleware returns in X-Trace-ID, so headers, body and store agree."""
    ctx = RagTracer.get_current_trace()
    return ctx.trace_id if ctx else None

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
                trace_id=_request_trace_id(),
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
            trace_id=_request_trace_id(),
        )
    except INFRASTRUCTURE_ERRORS as exc:
        # An outage must not be reported as "no relevant documents" (and must not open an escalation ticket);
        # an overload is refused with the time after which the client may retry.
        message, retry_after, busy = unavailable_reply(exc)
        (logger.warning if busy else logger.error)("RAG chat not served (%s): %s", "busy" if busy else "outage", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": type(exc).__name__, "message": message, "retry_after": retry_after},
            headers={"Retry-After": str(retry_after)},
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
            trace_id=_request_trace_id(),
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


@router.get("/sessions/{session_id}/agent-replies")
async def session_agent_replies(
    session_id: str,
    request: Request,
    since: float = Query(default=0.0, ge=0, description="Only replies written after this time (epoch seconds)"),
) -> Dict[str, Any]:
    """
    For the customer's own conversation: replies written by customer service after `since`, and how many of the
    conversation's questions still wait for one (the chat keeps checking only while some do).
    """
    tenant_id = _extract_tenant(request)
    user_id = _extract_user(request)
    sess = await session_use_case.get_session(session_id=session_id, user_id=user_id, tenant_id=tenant_id)
    if not sess or sess.tenant_id != tenant_id or sess.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat session not found")
    replies = [{"message_id": m.message_id, "content": m.content, "timestamp": m.timestamp}
               for m in sess.messages if m.author == "agent" and m.timestamp > since]
    pending = await _session_repo.count_open_tickets(tenant_id, sess.session_id)
    return {"replies": replies, "pending": pending}


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

    # The stored trace tells which stage produced the rated answer; rated traces feed the golden set.
    if payload.trace_id:
        trace = await _trace_store.get(payload.trace_id, tenant_id)
        if trace is not None:
            diagnosis = diagnose(trace, answer_correct=False if is_negative else True)
            feedback_record["trace_diagnosis"] = diagnosis.to_dict()
            await _trace_store.attach_feedback(payload.trace_id, tenant_id, {
                "feedback_id": feedback_id,
                "polarity": "negative" if is_negative else "positive",
                "rating": payload.rating,
                "text": payload.feedback_text or payload.comments,
                "error_category": payload.error_category,
                "diagnosed_stage": diagnosis.stage,
            })

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


def _require_admin(request: Request) -> None:
    """Traces and index snapshots expose passages and prompts: admins or the admin API key only."""
    api_key = request.headers.get("X-API-Key") or request.headers.get("Authorization", "")
    api_key = api_key[7:] if api_key.startswith("Bearer ") else api_key
    admin_key = getattr(rag_settings, "admin_api_key", None) or os.getenv("AIP_ADMIN_API_KEY", "")
    if is_admin(request) or (admin_key and hmac.compare_digest(api_key, admin_key)):
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin role required.")


@router.get("/traces/{trace_id}")
async def get_trace(trace_id: str, request: Request) -> Dict[str, Any]:
    """Full pipeline trace of one turn (stage inputs/outputs) with its stage diagnosis."""
    _require_admin(request)
    trace = await _trace_store.get(trace_id, _extract_tenant(request))
    if trace is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trace not found or expired")
    feedback = trace.get("feedback") or {}
    if feedback.get("polarity"):
        trace["diagnosis"] = diagnose(trace, answer_correct=feedback["polarity"] != "negative").to_dict()
    return trace


@router.get("/traces")
async def list_traces(
    request: Request,
    session_id: Optional[str] = Query(default=None),
    feedback: Optional[str] = Query(default=None, pattern="^(negative|positive|any)$"),
    limit: int = Query(default=50, ge=1, le=500),
) -> Dict[str, Any]:
    """Recent traces of the tenant: per session, or rated turns (e.g. feedback=negative to review)."""
    _require_admin(request)
    traces = await _trace_store.list(_extract_tenant(request), session_id=session_id, feedback=feedback, limit=limit)
    items = [
        {
            "trace_id": t.get("trace_id"), "session_id": t.get("session_id"), "created_at": t.get("created_at"),
            "query": t.get("query"), "intent": (t.get("outcome") or {}).get("intent"),
            "route": final_route(t), "is_refusal": (t.get("outcome") or {}).get("is_refusal"),
            "total_ms": t.get("total_ms"), "feedback": t.get("feedback"),
        }
        for t in traces
    ]
    return {"items": items, "count": len(items)}


@router.get("/eval/index-snapshot")
async def eval_index_snapshot(
    request: Request,
    doc_id: Optional[str] = Query(default=None),
    max_docs: int = Query(default=200, ge=1, le=1000),
) -> Dict[str, Any]:
    """
    Every indexed chunk (text + identifiers) of the tenant's documents, for offline evaluation: tells
    whether gold evidence survived parsing/chunking before blaming retrieval.
    """
    _require_admin(request)
    tenant_id = _extract_tenant(request)
    role = _extract_role(request)
    doc_ids = [doc_id] if doc_id else await _vector_store.list_document_ids(tenant_id=tenant_id, user_role=role, limit=max_docs)
    docs = []
    for d in doc_ids[:max_docs]:
        chunks = await _vector_store.fetch_document_chunks(doc_id=d, tenant_id=tenant_id, user_role=role, limit=5000)
        docs.append({"doc_id": d, "chunks": [chunk_ref(c, text_chars=100_000) for c in chunks]})
    return {"tenant_id": tenant_id, "documents": docs, "chunk_count": sum(len(d["chunks"]) for d in docs)}


@router.get("/feedback/dashboard")
async def get_feedback_dashboard(
    request: Request,
    limit: int = Query(default=200, ge=1, le=1000),
) -> Dict[str, Any]:
    """Executive 5-Stage Error Attribution Dashboard & Funnel Analysis (EXEC-RAG-04)."""
    tenant_id = _extract_tenant(request)
    records = await _session_repo.get_feedbacks(tenant_id=tenant_id, limit=limit)
    return error_attribution_service.generate_executive_dashboard(records)


class TicketUpdateDTO(BaseModel):
    status: Optional[str] = Field(default=None, pattern="^(open|resolved)$")
    note: Optional[str] = Field(default=None, max_length=2000)
    qa_id: Optional[str] = Field(default=None, max_length=64, description="Q&A pair added to answer it")


TICKET_REASONS = ("out_of_domain_or_insufficient_evidence", "handoff_request", "callback_request", "user_feedback")


@router.get("/tickets")
async def list_tickets(
    request: Request,
    status_filter: str = Query(default="open", alias="status", pattern="^(open|resolved|all)$"),
    reason: Optional[str] = Query(default=None, description="One of the ticket reasons; empty = all"),
    q: Optional[str] = Query(default=None, max_length=200),
    include_tests: bool = Query(default=False, description="Also show tickets of automated test sessions"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> Dict[str, Any]:
    """
    Inbox of what the bot could not answer (and handoff / callback / feedback requests) for the caller's
    knowledge base, newest first, so administrators can add the missing answer.
    """
    tenant_id = _extract_tenant(request)
    hidden = [] if include_tests else [p.strip() for p in rag_settings.ticket_hidden_session_prefixes.split(",")]
    result = await _session_repo.list_escalation_tickets(
        tenant_id,
        status=None if status_filter == "all" else status_filter,
        reasons=[reason] if reason in TICKET_REASONS else None,
        query=(q or "").strip() or None,
        hidden_session_prefixes=hidden,
        offset=(page - 1) * page_size,
        limit=page_size,
    )
    for t in result["items"]:
        t["status"] = t.get("status") or "open"
    return {**result, "page": page, "page_size": page_size}


@router.patch("/tickets/{ticket_id}")
async def update_ticket(ticket_id: str, payload: TicketUpdateDTO, request: Request) -> Dict[str, Any]:
    """Mark a ticket handled (or reopen it), optionally with a note and the Q&A pair that now answers it."""
    tenant_id = _extract_tenant(request)
    fields: Dict[str, Any] = {k: v for k, v in payload.model_dump().items() if v is not None}
    if payload.status == "resolved":
        fields["resolved_at"] = time.time()
        fields["resolved_by"] = extract_user(request)
    elif payload.status == "open":
        fields["resolved_at"] = None
    ticket = await _session_repo.update_escalation_ticket(ticket_id, tenant_id, fields)
    if ticket is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Ticket '{ticket_id}' not found")
    return ticket


TICKET_CONTEXT_MESSAGES = 8


@router.get("/tickets/{ticket_id}/conversation")
async def ticket_conversation(ticket_id: str, request: Request) -> Dict[str, Any]:
    """
    The ticket with the end of the conversation that led to it (the customer's turns, the bot's replies up to the
    ticket, and what customer service replied since), so customer service answers knowing what was asked.
    Conversations belong to end users: customer service / administrators of the ticket's tenant only.
    """
    if not is_support(request):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Reading conversations requires a support role")
    tenant_id = _extract_tenant(request)
    ticket = await _session_repo.get_escalation_ticket(ticket_id, tenant_id)
    if not ticket:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Ticket '{ticket_id}' not found")
    messages = []
    sess = await _ticket_session(ticket, tenant_id)
    if sess:
        until = float(ticket.get("created_at") or time.time()) + 120  # the bot's reply to that turn included
        kept = [m for m in sess.messages if m.timestamp <= until][-TICKET_CONTEXT_MESSAGES:]
        kept += [m for m in sess.messages if m.timestamp > until and m.author == "agent"]  # replies sent since
        messages = [{"role": m.role, "content": m.content, "timestamp": m.timestamp, "author": m.author} for m in kept]
    return {"ticket": ticket, "messages": messages}


async def _ticket_session(ticket: Dict[str, Any], tenant_id: str) -> Optional[ChatSessionDTO]:
    """The conversation a ticket came from; sessions are looked up by id only: never another tenant's."""
    if not ticket.get("session_id"):
        return None
    sess = await session_use_case.get_session(
        session_id=ticket["session_id"], user_id=ticket.get("user_id") or "", tenant_id=tenant_id
    )
    return sess if sess and sess.tenant_id == tenant_id else None


class TicketReplyDTO(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    resolve: bool = Field(default=True, description="Mark the ticket handled once the reply is delivered")


@router.post("/tickets/{ticket_id}/reply")
async def reply_to_ticket(ticket_id: str, payload: TicketReplyDTO, request: Request) -> Dict[str, Any]:
    """
    Customer service answers the customer whose question the bot could not answer: the reply is added to that
    customer's conversation (shown as written by customer service, never reused by the bot as an answer from the
    documents) and the ticket records it. Unlike a Q&A pair, nothing changes how the bot answers next time.
    """
    if not is_support(request):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Replying to customers requires a support role")
    tenant_id = _extract_tenant(request)
    ticket = await _session_repo.get_escalation_ticket(ticket_id, tenant_id)
    if not ticket:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Ticket '{ticket_id}' not found")
    sess = await _ticket_session(ticket, tenant_id)
    if not sess:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="The customer's conversation no longer exists: contact them another way")
    now = time.time()
    staff = extract_user(request)
    message = {"role": "assistant", "author": "agent", "content": payload.message.strip(), "ticket_id": ticket_id,
               "replied_by": staff, "timestamp": now}
    await _session_repo.append_message(sess.session_id, sess.user_id, tenant_id, message)
    fields: Dict[str, Any] = {"reply": message["content"], "replied_at": now, "replied_by": staff}
    if payload.resolve:
        fields.update(status="resolved", resolved_at=now, resolved_by=staff)
    updated = await _session_repo.update_escalation_ticket(ticket_id, tenant_id, fields)
    return {"ticket": updated or {**ticket, **fields}, "message": {k: message[k] for k in ("role", "author", "content", "timestamp")}}


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

