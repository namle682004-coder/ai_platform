"""
FastAPI REST Router for Enterprise Knowledge Base & Document Management.
Handles document upload, listing, status tracking, and deletion.
"""

import io
import logging
from typing import Any, Dict, Optional
from urllib.parse import quote

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)

from .rate_limiter import RateLimitDependency

from ...application.dtos import (
    DocumentListResponseDTO,
    DocumentResponseDTO,
    FeedbackRequestDTO,
    QACreateRequestDTO,
    QACreateResponseDTO,
    QADeleteResponseDTO,
)
from ...application.use_cases.knowledge_use_case import KnowledgeManagementUseCase
from ...domain.entities import DEFAULT_TENANT_ID, normalize_iso_date, normalize_tenant_id
from .identity import can_write_tenant, extract_role, extract_tenant, is_admin
from ...infrastructure.adapters.embedding_adapter import HttpEmbeddingAdapter
from ...infrastructure.adapters.qdrant_adapter import QdrantVectorStoreAdapter
from ...infrastructure.adapters.redis_cache_adapter import redis_cache
from ...infrastructure.adapters.storage_adapter import MinioStorageAdapter
from ...infrastructure.repositories.mongo_document_repo import MongoDocumentRepositoryAdapter

logger = logging.getLogger("aip-rag.api.knowledge")

router = APIRouter(prefix="/v1/knowledge", tags=["Knowledge & RAG"])

_upload_limiter = RateLimitDependency(requests_per_minute=300)
_read_limiter = RateLimitDependency(requests_per_minute=3000)

from ...config import rag_settings

_doc_repo = MongoDocumentRepositoryAdapter(mongo_uri=rag_settings.mongo_uri)
_storage = MinioStorageAdapter(
    endpoint=rag_settings.minio_endpoint,
    access_key=rag_settings.minio_root_user,
    secret_key=rag_settings.minio_root_password,
)
_vector_store = QdrantVectorStoreAdapter(base_url=rag_settings.qdrant_url, collection_name=rag_settings.collection_name)
_embedding_service = HttpEmbeddingAdapter(dim=rag_settings.embedding_dim)
from ...infrastructure.observability import rag_observability

knowledge_use_case = KnowledgeManagementUseCase(
    doc_repo=_doc_repo,
    storage=_storage,
    vector_store=_vector_store,
    embedding_service=_embedding_service,
    cache_service=redis_cache,
    observability_service=rag_observability,
)


_extract_tenant = extract_tenant


def _require_write_access(request: Request, tenant_id: str) -> None:
    if not can_write_tenant(request, tenant_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Writing to the shared knowledge base requires an admin role",
        )


async def _get_readable_document(doc_id: str, request: Request) -> Dict[str, Any]:
    """
    Load a document only if the caller may read it: same tenant (or the shared KB) and a
    matching role ACL. Returns 404 rather than 403 so document ids cannot be probed.
    """
    doc = await _doc_repo.get_document(doc_id)
    if doc:
        caller_tenant = _extract_tenant(request)
        doc_tenant = normalize_tenant_id(doc.get("tenant_id"))
        roles = doc.get("allowed_roles") or ["*"]
        tenant_ok = doc_tenant in (caller_tenant, DEFAULT_TENANT_ID)
        role_ok = "*" in roles or extract_role(request) in roles or is_admin(request)
        if tenant_ok and role_ok:
            return doc
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Document '{doc_id}' not found")


from ...infrastructure.adapters.rabbitmq_adapter import rabbitmq_broker


async def _dispatch_to_rabbitmq(task_payload: Dict[str, Any]) -> bool:
    """Dispatch document ingestion task to RabbitMQ worker queue with robust retry & self-healing."""
    queue_name = rag_settings.rag_queue
    success = await rabbitmq_broker.publish(
        queue_name=queue_name,
        payload={"payload": task_payload},
        max_retries=3,
    )
    if success:
        logger.info("Dispatched ingestion task for doc_id=%s to queue=%s", task_payload.get("doc_id"), queue_name)
    else:
        logger.warning("RabbitMQ broker unavailable after retries; doc_id=%s will require fallback processing", task_payload.get("doc_id"))
    return success


@router.post("/upload", response_model=DocumentResponseDTO, status_code=status.HTTP_201_CREATED, dependencies=[Depends(_upload_limiter)])
@router.post("/documents/upload", response_model=DocumentResponseDTO, status_code=status.HTTP_201_CREATED, dependencies=[Depends(_upload_limiter)])
async def upload_document(
    request: Request,
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    department: Optional[str] = Form(None),
    allowed_roles: Optional[str] = Form(None),
    effective_status: Optional[str] = Form("ACTIVE"),
    effective_date: Optional[str] = Form(None),
    expiry_date: Optional[str] = Form(None),
) -> DocumentResponseDTO:
    """Upload a raw document for asynchronous parsing, chunking, and vector indexing."""
    tenant_id = _extract_tenant(request)
    _require_write_access(request, tenant_id)
    roles = [r.strip() for r in allowed_roles.split(",") if r.strip()] if allowed_roles else ["*"]
    try:
        effective_date = normalize_iso_date(effective_date)
        expiry_date = normalize_iso_date(expiry_date)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    file_bytes = await file.read()
    filename = file.filename or "uploaded_document"

    try:
        doc_record = await knowledge_use_case.upload_document(
            file_bytes=file_bytes,
            filename=filename,
            title=title,
            department=department,
            allowed_roles=roles,
            tenant_id=tenant_id,
            effective_status=effective_status,
            effective_date=effective_date,
            expiry_date=expiry_date,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    # Dispatch ingestion task to RabbitMQ worker
    await _dispatch_to_rabbitmq(doc_record)

    doc_dto = await knowledge_use_case.get_document(doc_record["doc_id"])
    if not doc_dto:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to retrieve created document")
    return doc_dto


@router.get("/documents", response_model=DocumentListResponseDTO, dependencies=[Depends(_read_limiter)])
async def list_documents(
    request: Request,
    department: Optional[str] = Query(None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> DocumentListResponseDTO:
    """List indexed documents with pagination and tenancy isolation."""
    tenant_id = _extract_tenant(request)
    return await knowledge_use_case.list_documents(
        tenant_id=tenant_id,
        department=department,
        page=page,
        page_size=page_size,
    )


@router.get("/documents/{doc_id}", response_model=DocumentResponseDTO)
async def get_document(doc_id: str, request: Request) -> DocumentResponseDTO:
    """Retrieve document metadata and ingestion status."""
    await _get_readable_document(doc_id, request)
    doc = await knowledge_use_case.get_document(doc_id)
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Document '{doc_id}' not found")
    return doc


@router.get("/documents/{doc_id}/raw")
async def get_document_raw(doc_id: str, request: Request) -> Response:
    """Stream raw document binary from object storage (MinIO) for inline preview or download."""
    doc = await _get_readable_document(doc_id, request)

    s3_bucket = doc.get("s3_bucket", rag_settings.minio_bucket)
    s3_object_name = doc.get("s3_object_name")
    if not s3_object_name:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"No storage object for document '{doc_id}'")

    file_bytes = _storage.download_bytes(s3_bucket, s3_object_name)
    if not file_bytes:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"File binary not found in storage for '{doc_id}'")

    filename = doc.get("filename") or f"{doc_id}.bin"
    file_type = (doc.get("file_type") or "").lower()

    media_type = "application/octet-stream"
    if file_type == "pdf" or filename.endswith(".pdf"):
        media_type = "application/pdf"
    elif file_type == "md" or filename.endswith(".md"):
        media_type = "text/markdown; charset=utf-8"
    elif file_type == "txt" or filename.endswith(".txt"):
        media_type = "text/plain; charset=utf-8"
    elif file_type == "docx" or filename.endswith(".docx"):
        media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

    safe_filename = quote(filename.encode("utf-8"))
    headers = {
        "Content-Disposition": f"inline; filename*=UTF-8''{safe_filename}",
        "Content-Length": str(len(file_bytes)),
    }
    return Response(content=file_bytes, media_type=media_type, headers=headers)


@router.get("/documents/{doc_id}/content")
async def get_document_content(doc_id: str, request: Request) -> Dict[str, Any]:
    """Retrieve document metadata and extracted text content for rich web preview."""
    doc = await _get_readable_document(doc_id, request)

    filename = doc.get("filename", "")
    file_type = (doc.get("file_type") or "").lower()
    s3_bucket = doc.get("s3_bucket", rag_settings.minio_bucket)
    s3_object_name = doc.get("s3_object_name")

    content_text = ""
    if s3_object_name:
        file_bytes = _storage.download_bytes(s3_bucket, s3_object_name)
        if file_bytes:
            if file_type in ("md", "txt") or filename.endswith((".md", ".txt")):
                try:
                    content_text = file_bytes.decode("utf-8")
                except UnicodeDecodeError:
                    content_text = file_bytes.decode("utf-8", errors="replace")
            elif file_type == "docx" or filename.endswith(".docx"):
                try:
                    import zipfile
                    import xml.etree.ElementTree as ET
                    with zipfile.ZipFile(io.BytesIO(file_bytes)) as z:
                        xml_content = z.read("word/document.xml")
                        tree = ET.fromstring(xml_content)
                        texts = []
                        for p in tree.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p"):
                            p_text = "".join(t.text for t in p.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t") if t.text)
                            if p_text.strip():
                                texts.append(p_text.strip())
                        content_text = "\n\n".join(texts)
                except Exception as exc:
                    logger.warning("Could not extract docx text for %s: %s", doc_id, exc)
                    content_text = "(Không thể bóc tách bản xem trước dạng văn bản. Vui lòng tải file gốc về máy)"
            elif file_type == "pdf" or filename.endswith(".pdf"):
                content_text = f"[Tài liệu PDF: {filename}] Bạn có thể xem bản vẽ/trang đầy đủ qua trình đọc PDF trực tiếp bên trên."

    return {
        "doc_id": doc_id,
        "title": doc.get("title") or filename,
        "filename": filename,
        "file_type": file_type,
        "file_size_bytes": doc.get("file_size_bytes", 0),
        "total_chunks": doc.get("total_chunks", 0),
        "status": doc.get("status", "READY"),
        "content": content_text,
        "raw_url": f"/v1/knowledge/documents/{doc_id}/raw",
    }


@router.delete("/documents/{doc_id}", status_code=status.HTTP_200_OK)
async def delete_document(
    doc_id: str,
    request: Request,
) -> Dict[str, Any]:
    """Delete a document from vector index, object storage, and metadata database."""
    tenant_id = _extract_tenant(request)
    _require_write_access(request, tenant_id)
    deleted = await knowledge_use_case.delete_document(doc_id=doc_id, tenant_id=tenant_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Document '{doc_id}' not found")
    return {"status": "deleted", "doc_id": doc_id}


@router.post("/feedback")
async def record_feedback(payload: FeedbackRequestDTO) -> Dict[str, str]:
    """Collect human reinforcement feedback (Thumbs Up / Down) on RAG answers."""
    logger.info("Collected feedback for query '%s' rating=%d", payload.query[:40], payload.rating)
    return {"status": "recorded"}


@router.post("/qa", response_model=QACreateResponseDTO, status_code=status.HTTP_201_CREATED)
async def create_qa_entry(
    payload: QACreateRequestDTO,
    request: Request,
) -> QACreateResponseDTO:
    """
    Fast Q&A Vector Entry API (ING-RAG-06).
    Instant single-point embedding and indexing into Vector DB (< 30s) without full re-indexing.
    """
    tenant_id = _extract_tenant(request)
    _require_write_access(request, tenant_id)
    return await knowledge_use_case.ingest_qa(
        question=payload.question,
        answer=payload.answer,
        category=payload.category or "general",
        tags=payload.tags,
        allowed_roles=payload.allowed_roles,
        tenant_id=tenant_id,
        effective_status=payload.effective_status,
        effective_date=payload.effective_date,
        expiry_date=payload.expiry_date,
        question_variations=payload.question_variations,
    )


@router.delete("/qa/{qa_id}", response_model=QADeleteResponseDTO, status_code=status.HTTP_200_OK)
async def delete_qa_entry(
    qa_id: str,
    request: Request,
) -> QADeleteResponseDTO:
    """Delete a Q&A entry from Vector DB by qa_id (ING-RAG-06)."""
    tenant_id = _extract_tenant(request)
    _require_write_access(request, tenant_id)
    return await knowledge_use_case.delete_qa(qa_id=qa_id, tenant_id=tenant_id)

