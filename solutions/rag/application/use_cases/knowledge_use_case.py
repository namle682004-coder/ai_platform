"""
Enterprise Knowledge Base & Document Management Use Case.
Handles secure multi-tenant document registration, MinIO upload,
document listing with pagination, and complete cascading deletion.
"""

from __future__ import annotations

import logging
import os
import time
import uuid
from typing import Any, Dict, List, Optional

from ...domain.entities import (
    DEFAULT_TENANT_ID,
    DocumentChunk,
    DocumentStatus,
    normalize_tenant_id,
)
from ...domain.ports import (
    CachePort,
    DocumentRepositoryPort,
    EmbeddingPort,
    NullCacheAdapter,
    NullObservabilityAdapter,
    ObservabilityPort,
    StoragePort,
    VectorStorePort,
)
from ..dtos import (
    DocumentListResponseDTO,
    DocumentResponseDTO,
    QACreateResponseDTO,
    QADeleteResponseDTO,
)

logger = logging.getLogger("aip-rag.knowledge_use_case")

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md", ".json", ".csv"}
MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB


class KnowledgeManagementUseCase:
    """Document lifecycle management use case."""

    def __init__(
        self,
        doc_repo: DocumentRepositoryPort,
        storage: StoragePort,
        vector_store: VectorStorePort,
        embedding_service: Optional[EmbeddingPort] = None,
        cache_service: Optional[CachePort] = None,
        observability_service: Optional[ObservabilityPort] = None,
    ) -> None:
        self.doc_repo = doc_repo
        self.storage = storage
        self.vector_store = vector_store
        self.embedding_service = embedding_service
        self.cache_service = cache_service or NullCacheAdapter()
        self.obs = observability_service or NullObservabilityAdapter()

    async def _invalidate_tenant_cache(self, tenant_id: str, context: str) -> None:
        """Safely invalidate tenant cache across injected CachePort."""
        try:
            await self.cache_service.invalidate_tenant(tenant_id)
            logger.info("Invalidated cache for tenant=%s after %s", tenant_id, context)
        except Exception as exc:
            logger.warning("Failed to invalidate cache for tenant %s after %s: %s", tenant_id, context, exc)

    async def upload_document(
        self,
        file_bytes: bytes,
        filename: str,
        title: Optional[str] = None,
        department: Optional[str] = None,
        allowed_roles: Optional[List[str]] = None,
        tenant_id: str = DEFAULT_TENANT_ID,
        s3_bucket: str = "aip-data",
        effective_status: Optional[str] = "ACTIVE",
        effective_date: Optional[str] = None,
        expiry_date: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Validate, upload raw file to MinIO, and record PENDING status."""
        tenant_id = normalize_tenant_id(tenant_id)
        ext = os.path.splitext(filename)[1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise ValueError(f"Unsupported file format '{ext}'. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}")

        if len(file_bytes) > MAX_FILE_SIZE_BYTES:
            raise ValueError(f"File size exceeds maximum allowed 50MB ({len(file_bytes)} bytes)")

        doc_id = f"doc_{uuid.uuid4().hex[:12]}"
        s3_object_name = f"documents/{tenant_id}/{doc_id}_{filename}"

        s3_uri = self.storage.upload_bytes(
            bucket=s3_bucket,
            object_name=s3_object_name,
            data=file_bytes,
        )

        resolved_title = title.strip() if title and title.strip() not in ("", "string") else filename
        resolved_dept = department.strip() if department and department.strip() not in ("", "string") else None
        roles = allowed_roles or ["*"]

        now = int(time.time())
        doc_record = {
            "doc_id": doc_id,
            "tenant_id": tenant_id,
            "title": resolved_title,
            "filename": filename,
            "file_type": ext.lstrip("."),
            "file_size_bytes": len(file_bytes),
            "status": DocumentStatus.PENDING.value,
            "total_chunks": 0,
            "total_pages": 0,
            "department": resolved_dept,
            "allowed_roles": roles,
            "s3_bucket": s3_bucket,
            "s3_object_name": s3_object_name,
            "s3_uri": s3_uri,
            "effective_status": effective_status or "ACTIVE",
            "effective_date": effective_date,
            "expiry_date": expiry_date,
            "created_at": now,
            "updated_at": now,
        }

        await self.doc_repo.create_document(doc_record)
        return doc_record

    async def list_documents(
        self,
        tenant_id: str = DEFAULT_TENANT_ID,
        department: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> DocumentListResponseDTO:
        tenant_id = normalize_tenant_id(tenant_id)
        docs, total = await self.doc_repo.list_documents(
            tenant_id=tenant_id,
            department=department,
            page=page,
            page_size=page_size,
        )

        items = []
        for d in docs:
            created_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(d.get("created_at", time.time())))
            updated_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(d.get("updated_at", time.time())))
            items.append(
                DocumentResponseDTO(
                    doc_id=d["doc_id"],
                    tenant_id=d.get("tenant_id", tenant_id),
                    title=d.get("title", ""),
                    filename=d.get("filename", ""),
                    file_type=d.get("file_type", ""),
                    file_size_bytes=d.get("file_size_bytes", 0),
                    status=d.get("status", "PENDING"),
                    total_chunks=d.get("total_chunks", 0),
                    department=d.get("department"),
                    allowed_roles=d.get("allowed_roles", ["*"]),
                    created_at=created_at,
                    updated_at=updated_at,
                    s3_uri=d.get("s3_uri"),
                    effective_status=d.get("effective_status", "ACTIVE"),
                    effective_date=d.get("effective_date"),
                    expiry_date=d.get("expiry_date"),
                )
            )

        return DocumentListResponseDTO(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
        )

    async def get_document(self, doc_id: str) -> Optional[DocumentResponseDTO]:
        d = await self.doc_repo.get_document(doc_id)
        if not d:
            return None
        created_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(d.get("created_at", time.time())))
        updated_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(d.get("updated_at", time.time())))
        return DocumentResponseDTO(
            doc_id=d["doc_id"],
            tenant_id=d.get("tenant_id", ""),
            title=d.get("title", ""),
            filename=d.get("filename", ""),
            file_type=d.get("file_type", ""),
            file_size_bytes=d.get("file_size_bytes", 0),
            status=d.get("status", "PENDING"),
            total_chunks=d.get("total_chunks", 0),
            department=d.get("department"),
            allowed_roles=d.get("allowed_roles", ["*"]),
            created_at=created_at,
            updated_at=updated_at,
            s3_uri=d.get("s3_uri"),
            effective_status=d.get("effective_status", "ACTIVE"),
            effective_date=d.get("effective_date"),
            expiry_date=d.get("expiry_date"),
        )

    async def delete_document(self, doc_id: str, tenant_id: str = DEFAULT_TENANT_ID) -> bool:
        tenant_id = normalize_tenant_id(tenant_id)
        doc = await self.doc_repo.get_document(doc_id)
        if not doc:
            return False

        # 1. Delete points in Vector DB
        await self.vector_store.delete_by_doc_id(doc_id, tenant_id)

        # 2. Delete raw file in MinIO
        s3_bucket = doc.get("s3_bucket", "aip-data")
        s3_object_name = doc.get("s3_object_name")
        if s3_object_name:
            self.storage.delete_object(s3_bucket, s3_object_name)

        # 3. Delete document record in MongoDB
        deleted = await self.doc_repo.delete_document(doc_id, tenant_id)

        # 4. Invalidate Redis tenant cache (EXEC-RAG-06)
        await self._invalidate_tenant_cache(tenant_id, f"deleting doc={doc_id}")

        return deleted

    async def ingest_qa(
        self,
        question: str,
        answer: str,
        category: str = "general",
        tags: Optional[List[str]] = None,
        allowed_roles: Optional[List[str]] = None,
        tenant_id: str = DEFAULT_TENANT_ID,
        qa_id: Optional[str] = None,
        effective_status: Optional[str] = "ACTIVE",
        effective_date: Optional[str] = None,
        expiry_date: Optional[str] = None,
        question_variations: Optional[List[str]] = None,
    ) -> QACreateResponseDTO:
        """
        ING-RAG-06: Fast Q&A Ingestion & Instant Vector Indexing.
        Directly embeds the Q&A pair and writes point into Qdrant in < 30 seconds
        without triggering a full re-index of the knowledge base.
        Supports question_variations (BRD 3.4) for broader recall.
        """
        tenant_id = normalize_tenant_id(tenant_id)
        start_time = time.time()
        qa_id = qa_id or f"qa_{uuid.uuid4().hex[:8]}"
        tags = tags or []
        roles = allowed_roles or ["*"]
        variations = question_variations or []

        variations_block = ""
        if variations:
            variations_block = "\nCác biến thể câu hỏi: " + " | ".join(variations)
        formatted_text = f"[Hỏi - Đáp FAQ: {category}]\nCâu hỏi: {question}{variations_block}\nTrả lời: {answer}"

        if not self.embedding_service:
            raise RuntimeError("EmbeddingPort not provided to KnowledgeManagementUseCase for QA embedding.")

        if hasattr(self.embedding_service, "get_embedding"):
            vec = await self.embedding_service.get_embedding(formatted_text)
        elif hasattr(self.embedding_service, "batch_get_embeddings"):
            vec = (await self.embedding_service.batch_get_embeddings([formatted_text]))[0]
        else:
            vec = (await self.embedding_service.get_embeddings([formatted_text]))[0]

        chunk = DocumentChunk(
            chunk_id=f"{qa_id}_0",
            doc_id=qa_id,
            chunk_index=0,
            page_number=1,
            text=formatted_text,
            metadata={
                "is_faq": True,
                "qa_id": qa_id,
                "category": category,
                "approved_answer": answer,
                "question": question,
                "question_variations": variations,
                "tags": tags,
                "content_type": "faq",
                "heading": f"FAQ: {category}",
                "heading_path": f"FAQ > {category}",
                "strategy": "instant_qa",
                "effective_status": effective_status or "ACTIVE",
                "effective_date": effective_date,
                "expiry_date": expiry_date,
            },
        )

        await self.vector_store.upsert_chunks(
            chunks=[chunk],
            vectors=[vec],
            tenant_id=tenant_id,
            title=f"FAQ: {question[:50]}",
            filename=f"{qa_id}.faq",
            file_type="faq",
            department=category,
            allowed_roles=roles,
        )

        # Invalidate Redis tenant cache (EXEC-RAG-06)
        await self._invalidate_tenant_cache(tenant_id, f"instant QA ingestion={qa_id}")

        point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{qa_id}_0"))
        latency_ms = round((time.time() - start_time) * 1000, 2)

        return QACreateResponseDTO(
            status="indexed",
            qa_id=qa_id,
            indexing_latency_ms=latency_ms,
            qdrant_point_id=point_id,
        )

    async def delete_qa(self, qa_id: str, tenant_id: str = DEFAULT_TENANT_ID) -> QADeleteResponseDTO:
        """Deletes a Q&A pair from Vector DB by qa_id and invalidates tenant cache."""
        tenant_id = normalize_tenant_id(tenant_id)
        await self.vector_store.delete_by_doc_id(qa_id, tenant_id)
        await self._invalidate_tenant_cache(tenant_id, f"deleting QA={qa_id}")
        return QADeleteResponseDTO(status="deleted", qa_id=qa_id)

