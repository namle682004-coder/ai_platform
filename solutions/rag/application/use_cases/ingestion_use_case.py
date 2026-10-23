"""
Enterprise Document Ingestion Pipeline Use Case.
Orchestrates object storage download, parsing, chunking, PII redaction,
vector embedding generation, and Qdrant indexing.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from ...domain.entities import normalize_iso_date, normalize_tenant_id
from ...domain.exceptions import EmbeddingError, VectorStoreError
from ...domain.ports import (
    CachePort,
    DocumentParserPort,
    DocumentRepositoryPort,
    EmbeddingPort,
    NullCacheAdapter,
    NullObservabilityAdapter,
    ObservabilityPort,
    StoragePort,
    VectorStorePort,
)
from ..components.chunker import DocumentChunker
from ..components.acronym_harvester import acronym_harvester

logger = logging.getLogger("aip-rag.ingestion_use_case")


class DocumentIngestionUseCase:
    """Ingestion pipeline coordinator complying with Clean Architecture."""

    def __init__(
        self,
        doc_repo: DocumentRepositoryPort,
        storage: StoragePort,
        parser: DocumentParserPort,
        chunker: DocumentChunker,
        embedding_service: EmbeddingPort,
        vector_store: VectorStorePort,
        cache_service: Optional[CachePort] = None,
        observability_service: Optional[ObservabilityPort] = None,
    ) -> None:
        self.doc_repo = doc_repo
        self.storage = storage
        self.parser = parser
        self.chunker = chunker
        self.embedding_service = embedding_service
        self.vector_store = vector_store
        self.cache_service = cache_service or NullCacheAdapter()
        self.obs = observability_service or NullObservabilityAdapter()

    async def ingest_document(self, task_payload: Dict[str, Any]) -> Dict[str, Any]:
        doc_id = task_payload.get("doc_id") or task_payload.get("task_id", "")
        if not doc_id:
            logger.error("Missing doc_id in ingestion task payload: %s", task_payload)
            return {"status": "failed", "error": "Missing doc_id"}

        # Fetch metadata from MongoDB if not embedded in task envelope
        if not task_payload.get("s3_object_name"):
            doc_record = await self.doc_repo.get_document(doc_id)
            if doc_record:
                task_payload = {**doc_record, **task_payload}

        tenant_id = normalize_tenant_id(task_payload.get("tenant_id"))
        t_ingest_start = time.perf_counter()
        s3_bucket = task_payload.get("s3_bucket", "aip-data")
        s3_object_name = task_payload.get("s3_object_name", "")

        filename = (
            task_payload.get("filename")
            or (s3_object_name.split("/")[-1].split("_", 1)[-1] if s3_object_name else None)
            or task_payload.get("title", f"{doc_id}.txt")
        )
        file_type = task_payload.get("file_type") or (filename.split(".")[-1] if "." in filename else "text")
        raw_title = task_payload.get("title")
        title = filename if (not raw_title or raw_title.strip() in ("", "string")) else raw_title.strip()
        raw_dept = task_payload.get("department")
        department = None if (not raw_dept or raw_dept.strip() in ("", "string")) else raw_dept.strip()
        allowed_roles = task_payload.get("allowed_roles", ["*"])

        logger.info("Executing ingestion pipeline for doc_id=%s ('%s', %s)", doc_id, title, file_type)

        # 1. Update status: PROCESSING
        await self.doc_repo.update_document_status(doc_id, "PROCESSING")

        # 2. Download from MinIO
        file_bytes = self.storage.download_bytes(s3_bucket, s3_object_name)
        if not file_bytes:
            err = f"Failed to retrieve '{s3_object_name}' from bucket '{s3_bucket}'"
            logger.error(err)
            await self.doc_repo.update_document_status(doc_id, "FAILED", {"error": err})
            return {"status": "failed", "error": err, "doc_id": doc_id}

        # 3. Parse Document
        try:
            parsed_doc = self.parser.parse(file_bytes, filename)
        except Exception as exc:
            err = f"Parsing error for '{filename}': {exc}"
            logger.exception(err)
            await self.doc_repo.update_document_status(doc_id, "FAILED", {"error": err})
            return {"status": "failed", "error": err, "doc_id": doc_id}

        if not parsed_doc.pages or not parsed_doc.full_text():
            err = f"Document '{filename}' contained no readable text"
            logger.error(err)
            await self.doc_repo.update_document_status(doc_id, "FAILED", {"error": err})
            return {"status": "failed", "error": err, "doc_id": doc_id}

        full_doc_text = parsed_doc.full_text()

        # 3.1 Harvest Acronym Glossary (Stages 0-3: Explicit + Derived + Enterprise Dict)
        pipeline_res = acronym_harvester.harvest(full_doc_text)
        doc_glossary = pipeline_res.glossary
        logger.info(
            "Document %s harvested %d acronyms (coverage: unique=%.1f%%, mentions=%.1f%%)",
            doc_id,
            len(doc_glossary),
            pipeline_res.report.unique_coverage * 100,
            pipeline_res.report.mention_coverage * 100,
        )

        # 4. Chunk Document
        chunks = self.chunker.chunk_document(parsed_doc, doc_id, title=title)
        if not chunks:
            err = "Chunking produced 0 chunks"
            logger.error(err)
            await self.doc_repo.update_document_status(doc_id, "FAILED", {"error": err})
            return {"status": "failed", "error": err, "doc_id": doc_id}

        # Inject compliance & temporal status and enriched search text into chunk metadata (FR-RET-06 / RET-RAG-01)
        effective_status = task_payload.get("effective_status") or "ACTIVE"
        try:
            # Range filters need ISO dates; an unparseable expiry date would let an expired document through.
            effective_from = normalize_iso_date(task_payload.get("effective_from") or task_payload.get("effective_date"))
            effective_to = normalize_iso_date(task_payload.get("effective_to") or task_payload.get("expiry_date"))
        except ValueError as exc:
            err = f"Invalid validity date: {exc}"
            logger.error(err)
            await self.doc_repo.update_document_status(doc_id, "FAILED", {"error": err})
            return {"status": "failed", "error": err, "doc_id": doc_id}
        for c in chunks:
            c.metadata["effective_status"] = effective_status
            if effective_from:
                c.metadata["effective_from"] = effective_from
                c.metadata["effective_date"] = effective_from
            if effective_to:
                c.metadata["effective_to"] = effective_to
                c.metadata["expiry_date"] = effective_to

            # Enrich chunk text for search to eliminate Cross-Chunk Disconnection (RET-RAG-01)
            c.metadata["search_text"] = acronym_harvester.enrich_chunk_for_embedding(c.text, doc_glossary)

        logger.info("Document %s split into %d chunks (status=%s)", doc_id, len(chunks), effective_status)

        # 5-6. Vectorize (adapter batches requests) and index. Chunks are upserted in place first and
        #      only the leftover tail of a previous, longer version is removed afterwards, so a
        #      failure never leaves the document missing from the index.
        search_texts = [c.metadata.get("search_text", c.text) for c in chunks]
        try:
            vectors: List[List[float]] = await self.embedding_service.batch_get_embeddings(search_texts)
            upserted = await self.vector_store.upsert_chunks(
                chunks=chunks,
                vectors=vectors,
                tenant_id=tenant_id,
                title=title,
                filename=filename,
                file_type=file_type,
                department=department,
                allowed_roles=allowed_roles,
            )
            await self.vector_store.delete_stale_chunks(doc_id, tenant_id, keep_count=len(chunks))
        except (EmbeddingError, VectorStoreError) as exc:
            err = f"Indexing failed: {exc}"
            logger.error("Document %s: %s", doc_id, err)
            await self.doc_repo.update_document_status(doc_id, "FAILED", {"error": err})
            self.obs.record_ingestion(
                tenant_id=tenant_id,
                status="FAILED",
                duration=time.perf_counter() - t_ingest_start,
                chunk_count=len(chunks),
                file_type=file_type,
            )
            return {"status": "failed", "error": err, "doc_id": doc_id}

        # 7. Update status: INDEXED
        await self.doc_repo.update_document_status(
            doc_id,
            "INDEXED",
            {
                "total_chunks": len(chunks),
                "total_pages": len(parsed_doc.pages),
                "indexed_at": int(time.time()),
                "glossary": doc_glossary,
                "glossary_count": len(doc_glossary),
            },
        )
        logger.info("Document %s successfully indexed with %d points", doc_id, upserted)

        # 8. Invalidate tenant cache (EXEC-RAG-06)
        try:
            await self.cache_service.invalidate_tenant(tenant_id)
            logger.info("Invalidated cache for tenant=%s after ingesting doc=%s", tenant_id, doc_id)
        except Exception as exc:
            logger.warning("Failed to invalidate cache for tenant %s: %s", tenant_id, exc)

        duration = time.perf_counter() - t_ingest_start
        self.obs.record_ingestion(
            tenant_id=tenant_id,
            status="INDEXED",
            duration=duration,
            chunk_count=len(chunks),
            file_type=file_type,
        )

        return {
            "status": "completed",
            "doc_id": doc_id,
            "total_chunks": len(chunks),
            "indexed_points": upserted,
        }
