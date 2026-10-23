import pytest
import asyncio
from common.repositories.document_repository import MongoDocumentRepository
from common.chunking import TextChunker
from fastapi.testclient import TestClient
from src.main import app

client = TestClient(app)


def test_chunker_basic_split():
    chunker = TextChunker(chunk_size_chars=120, chunk_overlap_chars=20)
    sample_text = (
        "Đoạn văn thứ nhất nói về chính sách nghỉ phép của công ty AIP. Nhân viên có 12 ngày phép một năm.\n\n"
        "Đoạn văn thứ hai nói về tiền thưởng lễ Tết. Tiền thưởng được tính dựa trên hiệu suất công việc KPI.\n\n"
        "Đoạn văn thứ ba nói về bảo hiểm y tế cao cấp dành cho nhân sự chính thức."
    )
    chunks = chunker.split_text(sample_text)
    assert len(chunks) >= 3
    assert chunks[0]["chunk_index"] == 0
    assert "chính sách nghỉ phép" in chunks[0]["text"]
    assert "thưởng lễ Tết" in chunks[1]["text"]


def test_chunker_pii_masking():
    chunker = TextChunker(chunk_size_chars=500, mask_pii=True)
    text_with_pii = "Số CCCD của tôi là 038099012345 và email là namle@company.com liên hệ."
    chunks = chunker.split_text(text_with_pii)
    assert len(chunks) == 1
    assert "038099012345" not in chunks[0]["text"]
    assert ("[ID_REDACTED]" in chunks[0]["text"] or "******" in chunks[0]["text"])
    assert ("[EMAIL_REDACTED]" in chunks[0]["text"] or "[EMAIL_PROTECTED]" in chunks[0]["text"])


def test_document_repository_lifecycle():
    async def _run():
        repo = MongoDocumentRepository()
        doc_id = "test_doc_001"
        record = {
            "doc_id": doc_id,
            "tenant_id": "tenant_test",
            "title": "Sổ tay nhân viên 2026",
            "department": "HR",
        }
        created = await repo.create_document(record)
        assert created["doc_id"] == doc_id
        assert created["status"] == "QUEUED"

        fetched = await repo.get_document(doc_id, tenant_id="tenant_test")
        assert fetched is not None
        assert fetched["title"] == "Sổ tay nhân viên 2026"

        updated = await repo.update_document_status(doc_id, "INDEXED", {"total_chunks": 15})
        assert updated["status"] == "INDEXED"
        assert updated["total_chunks"] == 15

        count = await repo.count_documents(tenant_id="tenant_test")
        assert count >= 1

        deleted = await repo.delete_document(doc_id, tenant_id="tenant_test")
        assert deleted is True

    asyncio.run(_run())


def test_api_knowledge_list_documents():
    headers = {"Authorization": "Bearer aip_live_valid_test_key_12345"}
    res = client.get("/v1/knowledge/documents", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert "items" in data
    assert "total" in data


@pytest.mark.usefixtures("requires_embedding_runtime")
def test_api_rag_chat_anti_hallucination_guardrail():
    headers = {"Authorization": "Bearer aip_live_valid_test_key_12345"}
    # Query with high similarity threshold against empty/missing knowledge base
    res = client.post(
        "/v1/rag/chat",
        headers=headers,
        json={
            "query": "Hệ thống du hành vũ trụ của AIP bay đến sao Hỏa mất mấy ngày?",
            "similarity_threshold": 0.95,
        },
    )
    assert res.status_code == 200
    data = res.json()
    # Guardrail should trigger refusal since score < 0.95
    assert data["citations"] == []


def test_document_parser_factory():
    from solutions.rag.infrastructure.parsers.factory import parser_factory

    parser = parser_factory.get_parser("report.txt")
    sample_bytes = "Chương 1: Giới thiệu hệ thống Everwin AI Platform.".encode("utf-8")
    parsed = parser.parse(sample_bytes, "report.txt")
    assert len(parsed.pages) == 1
    assert "Everwin AI Platform" in parsed.pages[0].text
    assert parsed.pages[0].page_number == 1


def test_token_chunker_with_parsed_document():
    from solutions.rag.application.components.chunker import DocumentChunker
    from solutions.rag.domain.entities import ParsedDocument, ParsedPage

    pages = [
        ParsedPage(page_number=1, text="Chính sách bảo mật dữ liệu doanh nghiệp."),
        ParsedPage(page_number=2, text="Nhân viên cần bảo vệ mật khẩu và không chia sẻ token API."),
    ]
    parsed_doc = ParsedDocument(filename="security.txt", file_type="txt", pages=pages)
    chunker = DocumentChunker(child_chunk_size_chars=100, child_overlap_chars=20)
    chunks = chunker.chunk_document(parsed_doc, doc_id="doc_sec_01")

    assert len(chunks) == 2
    assert chunks[0].page_number == 1
    assert chunks[1].page_number == 2
    assert "chính sách" in chunks[0].text.lower()


def test_reranker_hybrid_overlap_boost():
    from common.retrieval.reranker import RerankerEngine
    from common.retrieval.retriever import RetrievedChunk

    reranker = RerankerEngine(threshold=0.50)
    candidates = [
        RetrievedChunk(
            doc_id="doc_1",
            chunk_index=0,
            title="Chính sách thưởng",
            page_number=1,
            score=0.60,
            text="Công ty có chính sách lương thưởng tháng 13 dựa trên hiệu suất KPI.",
        ),
        RetrievedChunk(
            doc_id="doc_2",
            chunk_index=0,
            title="Vệ sinh lao động",
            page_number=1,
            score=0.62,
            text="Quy định an toàn lao động trong văn phòng công ty.",
        ),
    ]

    # Query with heavy lexical overlap on "chính sách thưởng KPI"
    query = "Chính sách tiền thưởng KPI thế nào?"
    reranked = reranker.rerank(query, candidates, top_n=2)

    assert len(reranked) >= 1
    # doc_1 gets lexical boost over doc_2 despite slightly lower raw cosine score
    assert reranked[0].doc_id == "doc_1"
    assert reranked[0].score > 0.60


def test_structural_and_table_chunker():
    from common.chunking.token_chunker import TokenChunker
    from solutions.rag.domain.entities import ParsedDocument, ParsedPage

    table_markdown = (
        "| Ca trực | Thời gian | Cán bộ phụ trách |\n"
        "|---|---|---|\n"
        "| Ca 1 (Sáng) | 06:00 - 14:00 | Nguyễn Văn A |\n"
        "| Ca 2 (Chiều) | 14:00 - 22:00 | Trần Thị B |\n"
        "| Ca 3 (Đêm) | 22:00 - 06:00 | Lê Văn C |"
    )
    doc_text = (
        "Điều 1. Phân công ca trực và trách nhiệm nhân sự.\n\n"
        f"{table_markdown}\n\n"
        "Điều 2. Quy định bàn giao ca trực.\n"
        "Cán bộ giao ban phải ký biên bản bàn giao đầy đủ trước khi rời vị trí."
    )
    pages = [ParsedPage(page_number=1, text=doc_text)]
    doc = ParsedDocument(filename="ca_truc.txt", file_type="txt", pages=pages)

    chunker = TokenChunker(chunk_size_chars=500, chunk_overlap_chars=50)
    chunks = chunker.chunk_document(doc, doc_id="doc_shift_01")

    # Verify table is kept intact as dedicated chunk
    table_chunk = next((c for c in chunks if c.metadata.get("content_type") == "table"), None)
    assert table_chunk is not None
    assert "Ca 3 (Đêm)" in table_chunk.text
    assert "Nguyễn Văn A" in table_chunk.text

    # Verify section boundary separation
    assert any("Điều 1" in c.text for c in chunks)
    assert any("Điều 2" in c.text for c in chunks)


def test_rag_chat_stream_request_model():
    from solutions.rag.application.dtos import RagChatRequestDTO
    req = RagChatRequestDTO(query="Quy trình xử lý sự cố mất điện", stream=True)
    assert req.stream is True
    assert req.query == "Quy trình xử lý sự cố mất điện"


@pytest.mark.usefixtures("requires_embedding_runtime")
def test_swimlane_async_ingestion_and_rag_chat_e2e():
    """
    Validates complete Swimlane 1 & Swimlane 2 end-to-end:
    1. S3/MinIO upload of document bytes
    2. Mongo document record created in QUEUED status
    3. DocumentIngestionUseCase parses, chunks, vectorizes, upserts to Qdrant, updates to INDEXED
    4. Real-time RAG Chat queries knowledge base, retrieves chunks, passes guardrail,
       and returns grounded response with citations [1]
    5. Document delete API removes record and prunes Qdrant points
    """
    async def _run():
        from common.storage import minio_storage
        from common.repositories.document_repository import document_repository
        from solutions.rag.interfaces.worker.consumer import RagWorkerConsumer

        doc_id = "doc_swimlane_test_99"
        minio_storage._client = None
        tenant_id = "TENANT_RETAIL_BANK"
        filename = "chinh_sach_bao_mat_2026.txt"
        content_text = (
            "Chính sách bảo mật hệ thống AI Platform 2026: "
            "Tất cả nhân viên bắt buộc kích hoạt xác thực hai yếu tố 2FA và không chia sẻ API Key cho bên thứ ba. "
            "Mọi vi phạm an toàn thông tin sẽ bị khóa tài khoản ngay lập tức."
        )
        content_bytes = content_text.encode("utf-8")

        # 1. Upload to storage
        obj_name = f"knowledge/{tenant_id}/{doc_id}_{filename}"
        s3_uri, _ = minio_storage.upload_bytes(
            bucket=minio_storage.BUCKET_DATA,
            object_name=obj_name,
            data=content_bytes,
        )

        # 2. Create document record in Mongo (QUEUED)
        await document_repository.create_document({
            "doc_id": doc_id,
            "tenant_id": tenant_id,
            "title": "Chính sách bảo mật hệ thống 2026",
            "filename": filename,
            "file_type": ".txt",
            "file_size_bytes": len(content_bytes),
            "status": "QUEUED",
            "total_chunks": 0,
            "allowed_roles": ["*"],
            "s3_uri": s3_uri,
            "s3_object_name": obj_name,
            "s3_bucket": minio_storage.BUCKET_DATA,
        })

        # 3. Worker executes Ingestion Pipeline
        consumer = RagWorkerConsumer()
        task_payload = {
            "doc_id": doc_id,
            "tenant_id": tenant_id,
            "s3_bucket": minio_storage.BUCKET_DATA,
            "s3_object_name": obj_name,
            "file_type": ".txt",
            "title": "Chính sách bảo mật hệ thống 2026",
            "allowed_roles": ["*"],
        }
        res = await consumer.ingestion_use_case.ingest_document(task_payload)
        assert res["status"] == "completed"
        assert res["total_chunks"] >= 1

        # Verify Mongo status is now INDEXED
        doc_record = await document_repository.get_document(doc_id, tenant_id=tenant_id)
        assert doc_record is not None
        assert doc_record["status"] == "INDEXED"
        assert doc_record["total_chunks"] >= 1

        # 4. Swimlane 2: Real-time RAG Chat query matching this indexed knowledge
        import httpx
        headers = {"Authorization": "Bearer aip_live_valid_test_key_12345", "X-Tenant-ID": tenant_id}
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as ac:
            chat_res = await ac.post(
                "/v1/rag/chat",
                headers=headers,
                json={
                    "query": "Chính sách bảo mật hệ thống AI Platform 2026",
                    "similarity_threshold": 0.40,
                    "top_k": 3,
                },
            )
            assert chat_res.status_code == 200
            chat_data = chat_res.json()

            # Must be grounded with citations
            assert len(chat_data["citations"]) >= 1
            assert any(c["doc_id"] == doc_id for c in chat_data["citations"])

            # 5. Document Deletion & Qdrant pruning
            del_res = await ac.delete(f"/v1/knowledge/documents/{doc_id}", headers=headers)
            assert del_res.status_code == 200
            del_data = del_res.json()
            assert del_data["deleted"] is True

            # Verify document is 404 Not Found after deletion
            get_after_del = await ac.get(f"/v1/knowledge/documents/{doc_id}", headers=headers)
            assert get_after_del.status_code == 404

    asyncio.run(_run())


def test_rag_feedback_api_contract():
    headers = {"Authorization": "Bearer aip_live_valid_test_key_12345"}
    res = client.post(
        "/v1/rag/feedback",
        headers=headers,
        json={
            "trace_id": "tr_rag_test_123",
            "session_id": "sess_test_123",
            "rating": "like",
            "feedback_text": "Rất chính xác và đầy đủ ảnh minh họa",
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "recorded"
    assert data["feedback_id"].startswith("fb_rec_")


@pytest.mark.usefixtures("requires_embedding_runtime")
def test_rag_chat_circuit_breaker_escalation_payload():
    headers = {"Authorization": "Bearer aip_live_valid_test_key_12345"}
    res = client.post(
        "/v1/rag/chat",
        headers=headers,
        json={
            "query": "Hệ thống tàu vũ trụ vượt thời gian bay đến hố đen vũ trụ mất bao lâu?",
            "similarity_threshold": 0.95,
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["is_refusal"] is True
    assert data["circuit_breaker_triggered"] is True
    assert data["status"] == "escalation_required"
    assert data["escalation"] is not None
    assert data["escalation"]["status"] == "escalation_required"
    assert "hotline" in data["escalation"]["escalation_data"]
    assert data["telemetry"] is not None
    assert "trace_id" in data["telemetry"]




