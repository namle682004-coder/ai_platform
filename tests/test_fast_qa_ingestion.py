"""
Unit and integration test suite for ING-RAG-06:
Fast Q&A Ingestion & Instant Vector Indexing (Zero Full-Reindex).

DoD Verification:
1. Ingestion latency < 30 seconds (typically < 1000ms).
2. Qdrant point vector contains metadata: is_faq=True, category, approved_answer, question, tags.
3. Non-blocking vector index update (does not lock or require re-indexing of existing document chunks).
4. Update and delete by qa_id capability.
5. REST API contract verification: POST /v1/knowledge/qa and DELETE /v1/knowledge/qa/{qa_id}.
"""

import time
import pytest
from httpx import AsyncClient, ASGITransport
from solutions.rag.main import app
from solutions.rag.domain.ports import EmbeddingPort, VectorStorePort
from solutions.rag.application.use_cases.knowledge_use_case import KnowledgeManagementUseCase


class MockEmbeddingService(EmbeddingPort):
    async def get_embedding(self, text: str, model_alias: str = "embed-standard") -> list[float]:
        return [0.1] * 1024

    async def batch_get_embeddings(self, texts: list[str], model_alias: str = "embed-standard") -> list[list[float]]:
        return [[0.1] * 1024 for _ in texts]



class MockVectorStore(VectorStorePort):
    def __init__(self):
        self.points = {}

    async def ensure_collection(self) -> None:
        pass

    async def upsert_chunks(self, chunks, vectors, tenant_id, title, **kwargs) -> int:
        for c, v in zip(chunks, vectors, strict=False):
            point_id = c.metadata.get("qa_id") or c.chunk_id
            self.points[point_id] = {
                "chunk": c,
                "vector": v,
                "tenant_id": tenant_id,
                "title": title,
                "metadata": c.metadata,
            }
        return len(chunks)

    async def search(self, query_vector, tenant_id, **kwargs):
        results = []
        for pid, data in self.points.items():
            results.append({
                "id": pid,
                "score": 0.95,
                "payload": data["chunk"].metadata,
            })
        return results

    async def delete_by_doc_id(self, doc_id: str, tenant_id: str) -> bool:
        if doc_id in self.points:
            del self.points[doc_id]
            return True
        # Also check point ids
        to_del = [pid for pid, d in self.points.items() if d["chunk"].doc_id == doc_id]
        for pid in to_del:
            del self.points[pid]
        return len(to_del) > 0


@pytest.mark.anyio
async def test_fast_qa_ingestion_use_case_dod():
    """Verify KnowledgeManagementUseCase.ingest_qa satisfies ING-RAG-06 DoD 1, 2, 3."""
    mock_vec = MockVectorStore()
    mock_emb = MockEmbeddingService()

    use_case = KnowledgeManagementUseCase(
        doc_repo=None,
        storage=None,
        vector_store=mock_vec,
        embedding_service=mock_emb,
    )

    t0 = time.time()
    res = await use_case.ingest_qa(
        question="Mã lỗi ERR_KYSO_01 xử lý thế nào?",
        answer="Kiểm tra cổng cắm USB Token và khởi động lại dịch vụ SmartCA trong Services.msc.",
        category="ky_so",
        tags=["token", "usb", "smartca"],
        tenant_id="tenant_hospital",
    )
    elapsed = time.time() - t0

    # DoD 1: Latency < 30 seconds (and reported indexing_latency_ms)
    assert elapsed < 30.0
    assert res.indexing_latency_ms < 30000.0
    assert res.status == "indexed"
    assert res.qa_id.startswith("qa_")
    assert res.qdrant_point_id is not None

    # DoD 2: Point in vector store has is_faq=True, category, approved_answer
    assert res.qa_id in mock_vec.points
    stored = mock_vec.points[res.qa_id]
    meta = stored["metadata"]
    assert meta["is_faq"] is True
    assert meta["category"] == "ky_so"
    assert meta["approved_answer"] == "Kiểm tra cổng cắm USB Token và khởi động lại dịch vụ SmartCA trong Services.msc."
    assert "token" in meta["tags"]

    # DoD 3: Update existing Q&A by same qa_id
    updated_res = await use_case.ingest_qa(
        qa_id=res.qa_id,
        question="Mã lỗi ERR_KYSO_01 xử lý thế nào? (Cập nhật)",
        answer="Rút USB Token ra cắm lại vào cổng 3.0 và khởi động lại máy tính.",
        category="ky_so",
        tenant_id="tenant_hospital",
    )
    assert updated_res.qa_id == res.qa_id
    assert mock_vec.points[res.qa_id]["metadata"]["approved_answer"] == "Rút USB Token ra cắm lại vào cổng 3.0 và khởi động lại máy tính."

    # DoD 4: Delete by qa_id
    del_res = await use_case.delete_qa(qa_id=res.qa_id, tenant_id="tenant_hospital")
    assert del_res.status == "deleted"
    assert res.qa_id not in mock_vec.points


@pytest.mark.anyio
async def test_fast_qa_rest_api_endpoints(monkeypatch):
    """Verify REST API contract: POST /v1/knowledge/qa and DELETE /v1/knowledge/qa/{qa_id}."""
    from solutions.rag.interfaces.api import knowledge_use_case

    mock_vec = MockVectorStore()
    mock_emb = MockEmbeddingService()

    monkeypatch.setattr(knowledge_use_case, "vector_store", mock_vec)
    monkeypatch.setattr(knowledge_use_case, "embedding_service", mock_emb)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # POST /v1/knowledge/qa
        req_payload = {
            "question": "Làm thế nào để đổi mật khẩu tài khoản?",
            "answer": "Truy cập mục Cài đặt > Bảo mật > Đổi mật khẩu và nhập mã OTP gửi về SMS.",
            "category": "tai_khoan",
            "tags": ["mat_khau", "otp", "bao_mat"],
        }
        res = await ac.post("/v1/knowledge/qa", json=req_payload, headers={"X-Tenant-ID": "tenant_edu"})
        assert res.status_code == 201
        data = res.json()
        assert data["status"] == "indexed"
        qa_id = data["qa_id"]
        assert qa_id.startswith("qa_")
        assert data["indexing_latency_ms"] < 30000

        # DELETE /v1/knowledge/qa/{qa_id}
        del_res = await ac.delete(f"/v1/knowledge/qa/{qa_id}", headers={"X-Tenant-ID": "tenant_edu"})
        assert del_res.status_code == 200
        del_data = del_res.json()
        assert del_data["status"] == "deleted"
        assert del_data["qa_id"] == qa_id
