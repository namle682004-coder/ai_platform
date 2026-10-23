"""
Enterprise RAG Knowledge Base & Document Management API.

Handles secure multi-tenant document ingestion, lifecycle tracking,
MinIO object storage persistence, and RabbitMQ async dispatch.
"""

from __future__ import annotations

import io
import logging
import os
import uuid
import zipfile
import xml.etree.ElementTree as ET
from urllib.parse import quote
from typing import Any, Dict, List, Optional

import httpx
from common.repositories.document_repository import document_repository
from common.storage import minio_storage
from fastapi import (
    APIRouter,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)
from pydantic import BaseModel, Field

logger = logging.getLogger("aip-api.knowledge")

router = APIRouter(prefix="/v1/knowledge", tags=["Knowledge & RAG"])

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md", ".json", ".csv"}
MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB


class DocumentResponse(BaseModel):
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
    created_at: Any
    updated_at: Any
    s3_uri: Optional[str] = None


class DocumentListResponse(BaseModel):
    items: List[DocumentResponse]
    total: int
    page: int
    page_size: int


class FeedbackRequest(BaseModel):
    query: str
    response_text: str
    rating: int = Field(..., ge=-1, le=1, description="1 for Thumbs Up, -1 for Thumbs Down")
    comments: Optional[str] = None
    cited_doc_ids: List[str] = Field(default_factory=list)


def _extract_tenant(request: Request) -> str:
    """Extract tenant_id from auth request state, header, or fallback."""
    tenant = getattr(request.state, "tenant_id", None)
    if not tenant:
        tenant = request.headers.get("X-Tenant-ID") or request.headers.get("X-Tenant-Id")
    if not tenant or tenant.lower() in ("default_tenant", "tenant_default", "proj_default"):
        tenant = "global"
    if "," in tenant:
        tenant = tenant.split(",")[0].strip()
    return tenant


def _extract_user_role(request: Request) -> str:
    """Extract user role from auth request state."""
    return getattr(request.state, "role", "user")


@router.post(
    "/documents/upload",
    response_model=DocumentResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Upload & Ingest Document into Knowledge Base",
)
async def upload_document(
    request: Request,
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    department: Optional[str] = Form(None),
    allowed_roles: Optional[str] = Form("*"),
    wait_for_completion: bool = Query(True, description="Chờ worker hoàn tất indexing trước khi trả về"),
):
    """
    Upload a document (PDF, DOCX, TXT, MD), persist to MinIO,
    create MongoDB record, and queue background ingestion task via RabbitMQ.
    """
    tenant_id = _extract_tenant(request)

    # 1. Validate file extension
    filename = file.filename or "uploaded_file"
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file format '{ext}'. Allowed: {sorted(list(ALLOWED_EXTENSIONS))}",
        )

    # 2. Read content & validate size
    try:
        content = await file.read()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to read uploaded file: {exc}",
        ) from exc

    if len(content) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds maximum size limit of {MAX_FILE_SIZE_BYTES // (1024 * 1024)}MB",
        )

    doc_id = f"doc_{uuid.uuid4().hex[:12]}"
    clean_ext = ext.lstrip(".")
    
    # Standardize human-readable title
    clean_title = title.strip() if title and title.strip() not in ("", "string") else None
    if not clean_title:
        base_name = os.path.splitext(filename)[0]
        clean_title = base_name.replace("_", " ").replace("-", " ").strip()
    doc_title = clean_title
    
    # Standardize department (default to GENERAL if empty)
    clean_dept = department.strip() if department and department.strip() not in ("", "string") else None
    dept_val = clean_dept or "GENERAL"
    role_list = [r.strip() for r in (allowed_roles or "*").split(",") if r.strip()]

    # 3. Store in MinIO
    object_name = f"knowledge/{tenant_id}/{doc_id}_{filename}"
    s3_uri, _ = minio_storage.upload_bytes(
        bucket_name=minio_storage.BUCKET_DATA,
        object_name=object_name,
        data=content,
        content_type=file.content_type or "application/octet-stream",
    )

    # 4. Save metadata to MongoDB
    doc_record: Dict[str, Any] = {
        "doc_id": doc_id,
        "tenant_id": tenant_id,
        "title": doc_title,
        "filename": filename,
        "file_type": clean_ext,
        "file_size_bytes": len(content),
        "status": "QUEUED",
        "total_chunks": 0,
        "department": dept_val,
        "allowed_roles": role_list,
        "s3_uri": s3_uri,
        "s3_object_name": object_name,
        "s3_bucket": minio_storage.BUCKET_DATA,
    }

    created = await document_repository.create_document(doc_record)

    # 5. Dispatch task to RabbitMQ for async chunking & vector indexing
    pub = getattr(request.app.state, "task_publisher", None)
    if pub is not None:
        try:
            await pub.publish_task(
                task_id=doc_id,
                tenant_id=tenant_id,
                task_type="rag_ingestion",
                priority="normal",
                domain="rag",
                payload={
                    "doc_id": doc_id,
                    "tenant_id": tenant_id,
                    "s3_bucket": minio_storage.BUCKET_DATA,
                    "s3_object_name": object_name,
                    "filename": filename,
                    "file_type": clean_ext,
                    "title": doc_title,
                    "department": dept_val,
                    "allowed_roles": role_list,
                },
            )
            logger.info("Dispatched RAG ingestion task for doc_id=%s to RabbitMQ", doc_id)
        except Exception as exc:
            logger.error("Failed to publish task to RabbitMQ: %s. Document will remain QUEUED", exc)
    else:
        logger.warning("task_publisher unavailable; document %s saved but task not queued", doc_id)

    # 6. If wait_for_completion is requested, await worker indexing (up to 4.0s)
    if wait_for_completion and pub is not None:
        import asyncio
        for _ in range(40):
            await asyncio.sleep(0.1)
            updated_doc = await document_repository.get_document(doc_id, tenant_id)
            if updated_doc and updated_doc.get("status") in ("INDEXED", "FAILED"):
                return DocumentResponse(**updated_doc)

    return DocumentResponse(**created)


@router.get(
    "/documents",
    response_model=DocumentListResponse,
    summary="List Knowledge Base Documents",
)
async def list_documents(
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status_filter: Optional[str] = Query(None, alias="status"),
    department: Optional[str] = Query(None),
):
    """List documents for the current tenant with pagination."""
    tenant_id = _extract_tenant(request)
    skip = (page - 1) * page_size

    items = await document_repository.list_documents(
        tenant_id=tenant_id,
        skip=skip,
        limit=page_size,
        status=status_filter,
        department=department,
    )
    total = await document_repository.count_documents(tenant_id=tenant_id, status=status_filter)

    return DocumentListResponse(
        items=[DocumentResponse(**item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/documents/{doc_id}",
    response_model=DocumentResponse,
    summary="Get Document Details & Ingestion Status",
)
async def get_document(request: Request, doc_id: str):
    """Retrieve document status and chunk metrics."""
    tenant_id = _extract_tenant(request)
    doc = await document_repository.get_document(doc_id=doc_id, tenant_id=tenant_id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document '{doc_id}' not found",
        )
    return DocumentResponse(**doc)


@router.get(
    "/documents/{doc_id}/raw",
    summary="Stream raw document binary from object storage",
)
async def get_document_raw(request: Request, doc_id: str):
    """Stream raw document binary from object storage (MinIO) for inline preview or download."""
    tenant_id = _extract_tenant(request)
    doc = await document_repository.get_document(doc_id=doc_id, tenant_id=tenant_id)
    if not doc:
        doc = await document_repository.get_document(doc_id=doc_id)
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Document '{doc_id}' not found")

    s3_bucket = doc.get("s3_bucket", minio_storage.BUCKET_DATA)
    s3_object_name = doc.get("s3_object_name")
    if not s3_object_name:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"No storage object for document '{doc_id}'")

    file_bytes = minio_storage.download_bytes(s3_bucket, s3_object_name)
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


@router.get(
    "/documents/{doc_id}/content",
    summary="Retrieve document metadata and extracted text content for preview",
)
async def get_document_content(request: Request, doc_id: str):
    """Retrieve document metadata and extracted text content for rich web preview."""
    tenant_id = _extract_tenant(request)
    doc = await document_repository.get_document(doc_id=doc_id, tenant_id=tenant_id)
    if not doc:
        doc = await document_repository.get_document(doc_id=doc_id)
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Document '{doc_id}' not found")

    filename = doc.get("filename", "")
    file_type = (doc.get("file_type") or "").lower()
    s3_bucket = doc.get("s3_bucket", minio_storage.BUCKET_DATA)
    s3_object_name = doc.get("s3_object_name")

    content_text = ""
    if s3_object_name:
        file_bytes = minio_storage.download_bytes(s3_bucket, s3_object_name)
        if file_bytes:
            if file_type in ("md", "txt") or filename.endswith((".md", ".txt")):
                try:
                    content_text = file_bytes.decode("utf-8")
                except UnicodeDecodeError:
                    content_text = file_bytes.decode("utf-8", errors="replace")
            elif file_type == "docx" or filename.endswith(".docx"):
                try:
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
                    content_text = "(Không thể trích xuất văn bản từ file DOCX này. Vui lòng tải file gốc để xem)."
            elif file_type == "pdf" or filename.endswith(".pdf"):
                content_text = f"[Tài liệu PDF: {filename}] Bản xem trước trực quan được hiển thị phía trên qua trình đọc PDF."

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


@router.delete(
    "/documents/{doc_id}",
    status_code=status.HTTP_200_OK,
    summary="Delete Document & Prune Vectors from Qdrant",
)
async def delete_document(request: Request, doc_id: str):
    """Delete document from MongoDB and prune indexed vectors from Qdrant."""
    tenant_id = _extract_tenant(request)

    doc = await document_repository.get_document(doc_id=doc_id, tenant_id=tenant_id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document '{doc_id}' not found",
        )

    # 1. Delete from MongoDB
    deleted = await document_repository.delete_document(doc_id=doc_id, tenant_id=tenant_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete document '{doc_id}'",
        )

    # 2. Prune vector points in Qdrant (REST API delete points by filter)
    qdrant_url = os.getenv("QDRANT_URL", "http://qdrant:6333" if os.path.exists("/.dockerenv") else "http://127.0.0.1:6333")
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(
                f"{qdrant_url}/collections/aip_knowledge_base/points/delete",
                json={
                    "filter": {
                        "must": [
                            {"key": "doc_id", "match": {"value": doc_id}},
                            {"key": "tenant_id", "match": {"value": tenant_id}},
                        ]
                    }
                },
            )
            logger.info("Pruned points for doc_id=%s from Qdrant", doc_id)
    except Exception as exc:
        logger.warning("Failed to prune Qdrant points for doc_id=%s: %s", doc_id, exc)

    return {"deleted": True, "doc_id": doc_id, "message": "Document and associated vectors deleted"}


@router.post(
    "/feedback",
    status_code=status.HTTP_200_OK,
    summary="Record User Feedback for RAG Audit & Quality",
)
async def record_feedback(request: Request, body: FeedbackRequest):
    """Audit feedback for RAG quality evaluation."""
    tenant_id = _extract_tenant(request)
    data = body.model_dump()
    data["tenant_id"] = tenant_id
    saved = await document_repository.record_feedback(data)
    return {"status": "success", "feedback": saved}

