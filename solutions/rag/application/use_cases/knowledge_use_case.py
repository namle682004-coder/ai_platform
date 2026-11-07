"""
Enterprise Knowledge Base & Document Management Use Case.
Handles secure multi-tenant document registration, MinIO upload,
document listing with pagination, and complete cascading deletion.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import re
import time
import unicodedata
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

from ...domain.entities import (
    DEFAULT_TENANT_ID,
    SHARED_DEPARTMENT,
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
    NullTableStore,
    ObservabilityPort,
    StoragePort,
    TableStorePort,
    VectorStorePort,
)
from ..dtos import (
    DocumentListResponseDTO,
    DocumentResponseDTO,
    QACreateResponseDTO,
    QADeleteResponseDTO,
)

logger = logging.getLogger("aip-rag.knowledge_use_case")

# .xlsx is read by ExcelDocumentParser (openpyxl); legacy binary .xls is not supported by openpyxl.
ALLOWED_EXTENSIONS = {".pdf", ".docx", ".xlsx", ".html", ".htm", ".txt", ".md", ".json", ".csv"}
MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB
DEFAULT_DEPARTMENT = SHARED_DEPARTMENT
TERMINAL_STATUSES = frozenset({DocumentStatus.INDEXED.value, DocumentStatus.FAILED.value})


def _iso_timestamp(value: Any) -> str:
    """Render a stored timestamp as ISO-8601 UTC; records hold epoch seconds or ISO strings."""
    if isinstance(value, datetime):
        dt = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    elif isinstance(value, (int, float)):
        dt = datetime.fromtimestamp(value, tz=timezone.utc)
    elif isinstance(value, str) and value:
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return value
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = datetime.now(timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


_QA_COLUMN_NAMES = {
    # Checked in this order: "câu hỏi tương tự" is a variations column before it is a question column.
    "variations": ("cach hoi khac", "cau hoi tuong tu", "tuong tu", "bien the", "variations", "variants"),
    "category": ("danh muc", "chu de", "nhom", "phan loai", "category", "group", "topic"),
    "answer": ("cau tra loi", "tra loi", "dap an", "noi dung tra loi", "answer", "a"),
    "question": ("cau hoi", "hoi", "question", "q"),
}


def _plain(text: Any) -> str:
    """Lower case, no accents, words separated by single spaces ("Câu trả lời:" -> "cau tra loi")."""
    s = unicodedata.normalize("NFD", str(text or "")).replace("đ", "d").replace("Đ", "d")
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn").lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def qa_sheet_columns(header_row: Sequence[Any]) -> Tuple[Optional[int], Optional[int], Optional[int], Optional[int]]:
    """
    (question, answer, category, variations) column indexes of a Q&A sheet from its header row. A name matches
    as whole words ("Câu trả lời (bắt buộc)"); a one-letter name ("Q", "A") only as the whole header.
    """
    headers = [_plain(h) for h in header_row]
    found: Dict[str, int] = {}
    for role, names in _QA_COLUMN_NAMES.items():
        for i, h in enumerate(headers):
            if i in found.values() or not h:
                continue
            if any(h == n or (len(n) > 1 and f" {n} " in f" {h} ") for n in names):
                found[role] = i
                break
    return found.get("question"), found.get("answer"), found.get("category"), found.get("variations")


def _question_key(question: str) -> str:
    return _plain(question)


def _title_from_filename(filename: str) -> str:
    base_name = os.path.splitext(filename)[0]
    return base_name.replace("_", " ").replace("-", " ").strip() or filename


def _to_document_dto(d: Dict[str, Any], fallback_tenant: str = "") -> DocumentResponseDTO:
    return DocumentResponseDTO(
        doc_id=d["doc_id"],
        tenant_id=d.get("tenant_id", fallback_tenant),
        title=d.get("title", ""),
        filename=d.get("filename", ""),
        file_type=d.get("file_type", ""),
        file_size_bytes=d.get("file_size_bytes", 0),
        status=d.get("status", "PENDING"),
        total_chunks=d.get("total_chunks", 0),
        department=d.get("department"),
        allowed_roles=d.get("allowed_roles", ["*"]),
        created_at=_iso_timestamp(d.get("created_at")),
        updated_at=_iso_timestamp(d.get("updated_at")),
        s3_uri=d.get("s3_uri"),
        effective_status=d.get("effective_status", "ACTIVE"),
        effective_date=d.get("effective_date"),
        expiry_date=d.get("expiry_date"),
        version=int(d.get("version") or 1),
        replaces_doc_id=d.get("replaces_doc_id"),
        superseded_by=d.get("superseded_by"),
        deduplicated=bool(d.get("deduplicated", False)),
    )


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
        table_store: Optional[TableStorePort] = None,
    ) -> None:
        self.doc_repo = doc_repo
        self.storage = storage
        self.vector_store = vector_store
        self.table_store = table_store or NullTableStore()
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
        replaces_doc_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Validate, upload raw file to MinIO, and record PENDING status."""
        tenant_id = normalize_tenant_id(tenant_id)
        ext = os.path.splitext(filename)[1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise ValueError(f"Unsupported file format '{ext}'. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}")

        if len(file_bytes) > MAX_FILE_SIZE_BYTES:
            raise ValueError(f"File size exceeds maximum allowed 50MB ({len(file_bytes)} bytes)")

        roles = allowed_roles or ["*"]
        content_sha256 = hashlib.sha256(file_bytes).hexdigest()
        existing = await self.find_duplicate(tenant_id, content_sha256, roles)
        if existing is not None:
            # The same file is already in this knowledge base for the same audience: indexing it again would
            # put every passage twice in retrieval (duplicate sources, crowded context).
            logger.info(
                "Upload of '%s' to tenant=%s matches existing doc_id=%s (sha256=%s…); not re-indexed",
                filename, tenant_id, existing["doc_id"], content_sha256[:12],
            )
            return {**existing, "deduplicated": True}

        doc_id = f"doc_{uuid.uuid4().hex[:12]}"
        now = int(time.time())
        version = 1

        if replaces_doc_id:
            old_doc = await self.doc_repo.get_document(replaces_doc_id)
            if not old_doc or normalize_tenant_id(old_doc.get("tenant_id")) != tenant_id:
                raise ValueError(f"Document to replace '{replaces_doc_id}' not found in this tenant")
            version = int(old_doc.get("version") or 1) + 1
            if not title or title.strip() in ("", "string"):
                title = old_doc.get("title")
            if not department or department.strip() in ("", "string"):
                department = old_doc.get("department")
            # The old version stays searchable until this one is indexed (ingestion retires it then): a new
            # version still being parsed, or failing to, never leaves the knowledge base without the document.
            logger.info("Document %s will be replaced by new version %s (v%d) once indexed",
                        replaces_doc_id, doc_id, version)

        s3_object_name = f"documents/{tenant_id}/{doc_id}_{filename}"

        s3_uri = self.storage.upload_bytes(
            bucket=s3_bucket,
            object_name=s3_object_name,
            data=file_bytes,
        )

        resolved_title = title.strip() if title and title.strip() not in ("", "string") else _title_from_filename(filename)
        resolved_dept = department.strip() if department and department.strip() not in ("", "string") else DEFAULT_DEPARTMENT

        doc_record = {
            "doc_id": doc_id,
            "tenant_id": tenant_id,
            "title": resolved_title,
            "filename": filename,
            "file_type": ext.lstrip("."),
            "file_size_bytes": len(file_bytes),
            "content_sha256": content_sha256,
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
            "version": version,
            "replaces_doc_id": replaces_doc_id,
            "superseded_by": None,
            "created_at": now,
            "updated_at": now,
        }

        await self.doc_repo.create_document(doc_record)
        return doc_record

    async def find_duplicate(
        self, tenant_id: str, content_sha256: str, allowed_roles: List[str]
    ) -> Optional[Dict[str, Any]]:
        """
        A live record of the same file in the same tenant, visible to the same roles.

        Scope is the tenant only: another project's (or the shared base's) copy is a separate knowledge base.
        A copy restricted to other roles is kept apart too, otherwise users the new upload targets would not
        see it. A failed earlier attempt is not a duplicate: uploading again is how it is retried.
        """
        wanted = sorted(set(allowed_roles or ["*"]))
        for doc in await self.doc_repo.find_by_content_hash(tenant_id, content_sha256):
            if doc.get("status") == DocumentStatus.FAILED.value:
                continue
            if normalize_tenant_id(doc.get("tenant_id")) != normalize_tenant_id(tenant_id):
                continue
            if sorted(set(doc.get("allowed_roles") or ["*"])) == wanted:
                return doc
        return None

    async def list_documents(
        self,
        tenant_id: str = DEFAULT_TENANT_ID,
        department: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
        status: Optional[str] = None,
    ) -> DocumentListResponseDTO:
        tenant_id = normalize_tenant_id(tenant_id)
        docs, total = await self.doc_repo.list_documents(
            tenant_id=tenant_id,
            department=department,
            page=page,
            page_size=page_size,
            status=status,
        )

        return DocumentListResponseDTO(
            items=[_to_document_dto(d, tenant_id) for d in docs],
            total=total,
            page=page,
            page_size=page_size,
        )

    async def get_document(self, doc_id: str) -> Optional[DocumentResponseDTO]:
        d = await self.doc_repo.get_document(doc_id)
        if not d:
            return None
        return _to_document_dto(d)

    async def wait_for_indexing(self, doc_id: str, timeout_seconds: float, poll_interval: float = 0.1) -> Optional[DocumentResponseDTO]:
        """Poll until the worker marks the document INDEXED/FAILED or the timeout expires; returns the latest state."""
        deadline = time.monotonic() + max(0.0, timeout_seconds)
        while True:
            doc = await self.get_document(doc_id)
            if doc is None or doc.status in TERMINAL_STATUSES or time.monotonic() >= deadline:
                return doc
            await asyncio.sleep(poll_interval)

    async def delete_document(self, doc_id: str, tenant_id: str = DEFAULT_TENANT_ID) -> bool:
        tenant_id = normalize_tenant_id(tenant_id)
        doc = await self.doc_repo.get_document(doc_id)
        # Ownership check before touching vectors or object storage, so one tenant cannot
        # destroy another tenant's raw file.
        if not doc or normalize_tenant_id(doc.get("tenant_id")) != tenant_id:
            return False

        # 1. Delete points in Vector DB, and the document's stored tables
        await self.vector_store.delete_by_doc_id(doc_id, tenant_id)
        try:
            await self.table_store.delete_document(tenant_id, doc_id)
        except Exception as exc:  # noqa: BLE001 - logged; a later re-upload replaces them anyway
            logger.warning("Tables of doc=%s not deleted: %s", doc_id, exc)

        # 2. Delete raw file in MinIO
        s3_bucket = doc.get("s3_bucket", "aip-data")
        s3_object_name = doc.get("s3_object_name")
        if s3_object_name:
            self.storage.delete_object(s3_bucket, s3_object_name)
        # 2b. Its images: their signed URLs (in chat history too) stop resolving with the document.
        from ...config import rag_settings
        from ..components.media_assets import doc_prefix
        delete_prefix = getattr(self.storage, "delete_prefix", None)
        if delete_prefix is not None:
            delete_prefix(rag_settings.media_bucket or rag_settings.minio_bucket, doc_prefix(tenant_id, doc_id))

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
        created_at: Optional[int] = None,
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

        # People type without diacritics on phones ("gia ve xe buyt"): the unaccented form of every phrasing
        # is indexed too, so a pair matches however it is typed without the admin having to add it.
        from ..components.lexical_evidence import strip_diacritics

        phrasings = list(dict.fromkeys([question, *variations]))
        unaccented = [u for u in (strip_diacritics(p) for p in phrasings) if u and u not in phrasings]
        indexed_variations = list(dict.fromkeys([*variations, *unaccented]))
        variations_block = ""
        if indexed_variations:
            variations_block = "\nCác biến thể câu hỏi: " + " | ".join(indexed_variations)
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
                # An edit rewrites the point: the first creation time is carried over.
                "qa_created_at": int(created_at or start_time),
                "updated_at": int(start_time),
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

    async def list_qa(self, tenant_id: str = DEFAULT_TENANT_ID) -> List[Dict[str, Any]]:
        """The Q&A pairs administrators added to this tenant, newest first."""
        tenant_id = normalize_tenant_id(tenant_id)
        lister = getattr(self.vector_store, "list_faq_entries", None)
        if lister is None:
            return []
        out = []
        for p in await lister(tenant_id):
            qa_id = str(p.get("qa_id") or p.get("doc_id") or "")
            if not qa_id:
                continue
            out.append({
                "qa_id": qa_id,
                "question": str(p.get("question") or ""),
                "answer": str(p.get("approved_answer") or ""),
                "question_variations": list(p.get("question_variations") or []),
                "category": str(p.get("category") or "general"),
                "effective_status": p.get("effective_status") or "ACTIVE",
                "created_at": int(p.get("qa_created_at") or p.get("created_at") or 0),
                "updated_at": int(p.get("updated_at") or p.get("created_at") or 0),
            })
        return out

    async def update_qa(self, qa_id: str, tenant_id: str = DEFAULT_TENANT_ID, **fields: Any) -> QACreateResponseDTO:
        """Rewrites a Q&A pair in place (same point id), keeping when it was first created."""
        tenant_id = normalize_tenant_id(tenant_id)
        existing = next((e for e in await self.list_qa(tenant_id) if e["qa_id"] == qa_id), None)
        if existing is None:
            raise KeyError(qa_id)
        return await self.ingest_qa(qa_id=qa_id, tenant_id=tenant_id, created_at=existing["created_at"] or None, **fields)

    async def delete_qa(self, qa_id: str, tenant_id: str = DEFAULT_TENANT_ID) -> QADeleteResponseDTO:
        """Deletes a Q&A pair from Vector DB by qa_id and invalidates tenant cache."""
        tenant_id = normalize_tenant_id(tenant_id)
        await self.vector_store.delete_by_doc_id(qa_id, tenant_id)
        await self._invalidate_tenant_cache(tenant_id, f"deleting QA={qa_id}")
        return QADeleteResponseDTO(status="deleted", qa_id=qa_id)

    async def import_qa_from_excel(
        self,
        file_bytes: bytes,
        filename: str = "qa.xlsx",
        tenant_id: str = DEFAULT_TENANT_ID,
    ) -> Dict[str, Any]:
        """
        Bulk import Q&A pairs from an Excel workbook (.xlsx) (Requirement #19).
        Embeds and indexes each pair into the tenant's Vector DB.
        """
        import io
        import openpyxl

        tenant_id = normalize_tenant_id(tenant_id)
        wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
        ws = wb.active

        rows = list(ws.iter_rows(values_only=True))
        if not rows or len(rows) < 2:
            raise ValueError("Tệp Excel không có dữ liệu hoặc thiếu dòng tiêu đề.")

        q_idx, a_idx, cat_idx, var_idx = qa_sheet_columns(rows[0])
        if q_idx is None or a_idx is None:
            raise ValueError("Không nhận ra cột câu hỏi và cột câu trả lời: dòng đầu cần có tiêu đề "
                             "\"Câu hỏi\" và \"Câu trả lời\" (hoặc \"Question\", \"Answer\").")

        # A pair whose question is already in this knowledge base is not added twice (re-importing a file).
        known = {_question_key(q.get("question", "")) for q in await self.list_qa(tenant_id)}

        imported = 0
        failed = 0
        skipped = 0
        errors = []
        created_items = []

        for row_idx, row in enumerate(rows[1:], start=2):
            if not row or all(v is None or str(v).strip() == "" for v in row):
                continue
            q_val = str(row[q_idx] or "").strip() if q_idx < len(row) and row[q_idx] is not None else ""
            a_val = str(row[a_idx] or "").strip() if a_idx < len(row) and row[a_idx] is not None else ""

            if not q_val or not a_val:
                failed += 1
                errors.append(f"Dòng {row_idx}: Thiếu câu hỏi hoặc câu trả lời")
                continue
            if _question_key(q_val) in known:
                skipped += 1
                continue
            known.add(_question_key(q_val))

            category = "general"
            if cat_idx is not None and cat_idx < len(row) and row[cat_idx]:
                category = str(row[cat_idx]).strip() or "general"

            variations = []
            if var_idx is not None and var_idx < len(row) and row[var_idx]:
                raw_vars = str(row[var_idx]).replace("\n", "|").split("|")
                variations = [v.strip() for v in raw_vars if v.strip()]

            try:
                qa_res = await self.ingest_qa(
                    question=q_val,
                    answer=a_val,
                    category=category,
                    tenant_id=tenant_id,
                    question_variations=variations,
                )
                imported += 1
                created_items.append({"qa_id": qa_res.qa_id, "question": q_val, "category": category})
            except Exception as exc:
                failed += 1
                errors.append(f"Dòng {row_idx}: Lỗi nạp ({exc})")

        return {
            "total_rows": len(rows) - 1,
            "imported": imported,
            "skipped_existing": skipped,
            "failed": failed,
            "errors": errors,
            "items": created_items,
        }


