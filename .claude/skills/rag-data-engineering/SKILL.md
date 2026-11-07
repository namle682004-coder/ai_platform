---
name: rag-data-engineering
description: Document ingestion for AIP RAG — upload, duplicate documents across accounts/tenants, PDF/DOCX/Excel parsing, images, chunking (parent/child), acronym harvesting, metadata, embedding and Qdrant indexing, re-indexing and deletion. Use when a fact is missing from the index, a document is duplicated, parsing is garbled, chunks split wrongly, or an upload/worker job fails.
---

# RAG Data Engineering

Phạm vi: từ lúc file được upload đến lúc chunk nằm trong Qdrant. Nếu căn cứ **không có trong `GET /v1/rag/eval/index-snapshot`** thì lỗi thuộc skill này.

## Luồng ingestion hiện tại

```
POST /v1/knowledge/upload  (interfaces/api/knowledge_router.py)
  → KnowledgeUseCase.upload_document   (application/use_cases/knowledge_use_case.py)
      kiểm tra đuôi file và kích thước (50MB) → doc_id = doc_<uuid12> → MinIO documents/{tenant}/{doc_id}_{filename}
      → Mongo record status=PENDING
  → RabbitMQ → worker (make dev-rag-worker, interfaces/worker/consumer.py)
  → DocumentIngestionUseCase.ingest_document   (application/use_cases/ingestion_use_case.py)
      PROCESSING → tải từ MinIO → parser (infrastructure/parsers/factory.py: pdf/docx/excel/text)
      → _store_images (MinIO, media_assets.py) → acronym_harvester.harvest
      → DocumentChunker.chunk_document (application/components/chunker.py, packages/common/common/chunking)
      → metadata: effective_status / effective_from / effective_to, allowed_roles, department
      → embedding (embedding_adapter.py) → qdrant_adapter.upsert_chunks → INDEXED / FAILED
```

Cấu hình chunk nằm trong `solutions/rag/config.py`: `RAG_CHUNK_SIZE`, `RAG_CHUNK_OVERLAP`, `RAG_CHILD_CHUNK_SIZE`, `RAG_CHILD_OVERLAP`, `RAG_PARENT_CHUNK_SIZE`.

## Vấn đề đã biết: upload trùng

`upload_document` luôn sinh `doc_id` ngẫu nhiên và **không kiểm tra nội dung**. Vì vậy cùng một file upload hai lần, dù từ một hay hai tài khoản, đều tạo hai bộ chunk. Retrieval sau đó trả về các passage gần như trùng nhau, chiếm chỗ trong top-k và gây trích dẫn lặp ([1], [2] cùng nguồn).

Hướng sửa chuẩn (tổng quát, không theo tên file):
- Tính `content_sha256` của bytes khi upload, lưu vào Mongo record và vào payload của chunk.
- Phạm vi dedup **trong cùng `tenant_id`**. Khác tenant thì không được gộp, vì đó là vi phạm cách ly. Cùng tenant thì trả về document đã có, hoặc hỏi người dùng muốn thay thế phiên bản không.
- Cần index Mongo trên `(tenant_id, content_sha256)`. Dữ liệu cũ cần một script backfill riêng.
- Ở tầng retrieval vẫn nên có bước khử passage gần trùng (xem skill `rag-retrieval`), vì hai phiên bản khác nhau của cùng một tài liệu vẫn có thể giống nhau phần lớn.

## Checklist khi sửa parser hoặc chunker

1. Tái hiện bằng chính file lỗi. Parse rồi in các trang và chunk ra, xem heading, bảng, ảnh có còn đúng không.
2. Bảng: giữ được cấu trúc hàng và cột (`table_rows.py`, `numeric_tables.py` dựa vào cấu trúc này). Liên quan có `tests/test_html_table_multi_strategy.py`.
3. Heading và breadcrumb: `chunker.py` có các luật nhận dạng heading. Không được thêm luật dựa vào từ ngữ của một tài liệu cụ thể.
4. Ảnh: hash SHA-256 trong `pdf_parser.py` / `docx_parser.py`, URL ký bằng HMAC (`media_assets.py`). Ảnh phải gắn vào đúng passage.
5. Tiếng Việt: giữ nguyên dấu, chuẩn hóa Unicode NFC. Liên quan có `vietnamese_resources.py` và `tests/test_diacritics_restoration.py`.
6. Đổi chunking thì **phải re-index** các tài liệu bị ảnh hưởng (`delete_by_doc_id` / `delete_stale_chunks` trong `qdrant_adapter.py`) và ghi rõ điều đó trong PR.

## Test liên quan

`tests/test_chunking_strategies.py`, `test_universal_structure_chunker.py`, `test_parent_windowing.py`, `test_fast_qa_ingestion.py`, `test_rag_knowledge_management.py`, `test_rag_document_images.py`, `test_qdrant_payload.py`, `test_pii_sanitization.py`, `test_tenant_id_consistency.py`, `test_temporal_filter.py`.

## Không được làm

- Gộp hoặc dedup tài liệu giữa các tenant.
- Thay đổi tên field trong payload Qdrant mà không cập nhật `_build_filter_conditions` và không re-index.
- Bỏ qua bước che PII (`PiiSanitizer`).
