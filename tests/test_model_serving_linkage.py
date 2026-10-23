"""
Model-serving linkage & failure semantics for the RAG solution.

Covers: alias resolution order, embedding/reranker adapters against the embedding-server
contract (no synthetic fallback vectors), Qdrant failure surfacing, cache keying, date
normalisation, and the gateway alias / identity fixes.
"""

import asyncio
import json

import httpx
import pytest

from solutions.rag.domain.entities import normalize_iso_date
from solutions.rag.domain.exceptions import EmbeddingError, RerankerError, VectorStoreError
from solutions.rag.infrastructure.adapters.embedding_adapter import HttpEmbeddingAdapter
from solutions.rag.infrastructure.adapters.model_registry import (
    ModelEndpointNotFoundError,
    ModelEndpointResolver,
)
from solutions.rag.infrastructure.adapters.qdrant_adapter import QdrantVectorStoreAdapter
from solutions.rag.infrastructure.adapters.reranker_adapter import HttpCrossEncoderReranker


def _resolver(aliases=None) -> ModelEndpointResolver:
    resolver = ModelEndpointResolver(mongo_uri="", cache_ttl_seconds=3600)
    resolver._cache = aliases or {}
    resolver._cache_loaded_at = float("inf")  # never refresh from MongoDB in unit tests
    return resolver


def _mock_client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


# --------------------------------------------------------------------------- alias resolution


def test_resolver_prefers_override_then_mongodb_then_catalog():
    async def _run():
        mongo = {"embed-standard": {"alias_name": "embed-standard", "target_url": "http://gpu:8012/v1/", "status": "enabled",
                                    "physical_model": "BAAI/bge-m3"}}
        resolver = _resolver(mongo)

        override = await resolver.resolve("embed-standard", override_url="http://localhost:9999/v1")
        assert (override.base_url, override.source) == ("http://localhost:9999/v1", "override")

        from_db = await resolver.resolve("embed-standard")
        assert (from_db.base_url, from_db.source, from_db.physical_model) == ("http://gpu:8012/v1", "mongodb", "BAAI/bge-m3")

        from_catalog = await resolver.resolve("rerank-standard")
        assert from_catalog.source == "catalog"
        assert from_catalog.physical_model == "BAAI/bge-reranker-v2-m3"

    asyncio.run(_run())


def test_resolver_rejects_disabled_and_unknown_aliases():
    async def _run():
        resolver = _resolver({"embed-standard": {"alias_name": "embed-standard", "target_url": "http://x/v1", "status": "disabled"}})
        with pytest.raises(ModelEndpointNotFoundError):
            await resolver.resolve("embed-standard")
        with pytest.raises(ModelEndpointNotFoundError):
            await resolver.resolve("no-such-alias")

    asyncio.run(_run())


# --------------------------------------------------------------------------- embeddings


def test_embedding_adapter_calls_alias_endpoint_and_batches():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        calls.append((str(request.url), body["model"], len(body["input"])))
        data = [{"index": i, "embedding": [0.1] * 4} for i in range(len(body["input"]))]
        return httpx.Response(200, json={"data": data, "model": body["model"]})

    async def _run():
        adapter = HttpEmbeddingAdapter(dim=4, base_url="", batch_size=2, resolver=_resolver(
            {"embed-standard": {"alias_name": "embed-standard", "target_url": "http://gpu:8012/v1", "status": "enabled"}}))
        adapter._client = _mock_client(handler)
        vectors = await adapter.batch_get_embeddings(["a", "b", "c"])
        assert len(vectors) == 3
        assert calls == [("http://gpu:8012/v1/embeddings", "embed-standard", 2), ("http://gpu:8012/v1/embeddings", "embed-standard", 1)]

    asyncio.run(_run())


def test_embedding_adapter_raises_instead_of_fabricating_vectors():
    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    def wrong_dim(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": [{"index": 0, "embedding": [0.1] * 1536}]})

    async def _run():
        for handler, message in ((down, "unavailable"), (wrong_dim, "dimension mismatch")):
            adapter = HttpEmbeddingAdapter(dim=1024, base_url="http://gpu:8012/v1", resolver=_resolver())
            adapter._client = _mock_client(handler)
            with pytest.raises(EmbeddingError, match=message):
                await adapter.get_embedding("hóa đơn điện tử")

    asyncio.run(_run())


# --------------------------------------------------------------------------- reranker


def test_remote_reranker_maps_scores_and_applies_threshold():
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["model"] == "rerank-standard"
        assert body["documents"][0].startswith("[Tài liệu: Quy chế]")
        return httpx.Response(200, json={"results": [
            {"index": 1, "relevance_score": 0.93},
            {"index": 0, "relevance_score": 0.88},
            {"index": 2, "relevance_score": 0.05},
        ], "model": "rerank-standard"})

    candidates = [
        {"id": i, "score": 0.5, "payload": {"title": "Quy chế", "text": f"đoạn {i}", "doc_id": f"d{i}"}}
        for i in range(3)
    ]

    async def _run():
        reranker = HttpCrossEncoderReranker(base_url="http://gpu:8012/v1", resolver=_resolver())
        reranker._client = _mock_client(handler)
        ranked = await reranker.arerank("quy chế nghỉ phép", candidates, top_n=3, min_threshold=0.75)
        assert [c["payload"]["doc_id"] for c in ranked] == ["d1", "d0"]
        assert ranked[0]["score"] == 0.93 and ranked[0]["cross_encoder_rank"] == 1

    asyncio.run(_run())


def test_remote_reranker_failure_raises():
    def down(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"detail": "loading"})

    async def _run():
        reranker = HttpCrossEncoderReranker(base_url="http://gpu:8012/v1", resolver=_resolver())
        reranker._client = _mock_client(down)
        with pytest.raises(RerankerError):
            await reranker.arerank("q", [{"payload": {"text": "t"}}])

    asyncio.run(_run())


# --------------------------------------------------------------------------- qdrant


def test_dense_search_surfaces_outage_but_missing_collection_is_empty():
    async def _run():
        adapter = QdrantVectorStoreAdapter(base_url="http://qdrant:6333", collection_name="kb", dim=4)

        adapter._http_client = _mock_client(lambda r: (_ for _ in ()).throw(httpx.ConnectError("down", request=r)))
        with pytest.raises(VectorStoreError):
            await adapter.search_dense([0.1] * 4, tenant_id="t1")

        adapter._http_client = _mock_client(lambda r: httpx.Response(500, text="boom"))
        with pytest.raises(VectorStoreError):
            await adapter.search_dense([0.1] * 4, tenant_id="t1")

        adapter._http_client = _mock_client(lambda r: httpx.Response(404, json={"status": {"error": "Not found"}}))
        assert await adapter.search_dense([0.1] * 4, tenant_id="t1") == []

    asyncio.run(_run())


def test_sparse_vectors_use_binary_query_weights_and_vietnamese_bigrams():
    query = QdrantVectorStoreAdapter.compute_sparse_query_vector("bảo hiểm xã hội")
    assert set(query["values"]) == {1.0}
    # 4 syllables + 3 adjacent bigrams ("bảo hiểm", "hiểm xã", "xã hội")
    assert len(query["indices"]) == 7

    doc = QdrantVectorStoreAdapter.compute_sparse_vector("bảo hiểm xã hội bảo hiểm")
    assert all(0.0 < v < 3.0 for v in doc["values"])
    assert QdrantVectorStoreAdapter.compute_sparse_vector("a b c") == {"indices": [], "values": []}


def test_ensure_collection_enables_idf_and_datetime_indexes_on_existing_collection():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path, json.loads(request.content) if request.content else None))
        if request.method == "GET":
            return httpx.Response(200, json={"result": {
                "config": {"params": {"sparse_vectors": {"text-sparse": {}}}},
                "payload_schema": {"tenant_id": {"data_type": "keyword"}, "effective_to": {"data_type": "keyword"}},
            }})
        return httpx.Response(200, json={"result": True})

    async def _run():
        adapter = QdrantVectorStoreAdapter(base_url="http://qdrant:6333", collection_name="kb", dim=4)
        adapter._http_client = _mock_client(handler)
        await adapter.ensure_collection()

    asyncio.run(_run())
    assert ("PATCH", "/collections/kb", {"sparse_vectors": {"text-sparse": {"modifier": "idf"}}}) in seen
    assert ("DELETE", "/collections/kb/index/effective_to", None) in seen
    created = {(b["field_name"], str(b["field_schema"])) for m, p, b in seen if m == "PUT" and b}
    assert ("effective_to", "datetime") in created and ("expiry_date", "datetime") in created
    assert not any(b and b.get("field_name") == "tenant_id" for m, p, b in seen if m == "PUT")


# --------------------------------------------------------------------------- dates


@pytest.mark.parametrize("raw,expected", [
    ("15/04/2024", "2024-04-15"),
    ("2024-4-5", "2024-04-05"),
    ("2024-04-05T10:00:00Z", "2024-04-05"),
    ("", None),
    (None, None),
])
def test_normalize_iso_date(raw, expected):
    assert normalize_iso_date(raw) == expected


@pytest.mark.parametrize("raw", ["31/02/2024", "next monday", "2024/13/01"])
def test_normalize_iso_date_rejects_invalid(raw):
    with pytest.raises(ValueError):
        normalize_iso_date(raw)


# --------------------------------------------------------------------------- cache keying


def test_cache_get_and_set_share_key_and_follow_ups_use_standalone_query():
    from solutions.rag.application.dtos import RagChatRequestDTO
    from solutions.rag.application.use_cases.chat_use_case import RagChatUseCase

    use_case = RagChatUseCase.__new__(RagChatUseCase)
    req = RagChatRequestDTO(query="nó cần giấy tờ gì?")
    args = use_case._cache_key_args(req, "hoàn thuế cần giấy tờ gì?", "t1", "user")
    assert args["combine_strategy"] == "auto"
    assert args["query"] == "hoàn thuế cần giấy tờ gì?"
    assert RagChatUseCase._is_cacheable(req)
    assert not RagChatUseCase._is_cacheable(RagChatRequestDTO(query="abc", doc_ids=["d1"]))


# --------------------------------------------------------------------------- gateway


def test_gateway_db_alias_overrides_env_default_but_catalog_alias_does_not():
    from src.items.alias_router import AliasRouterService

    router = AliasRouterService()
    router._registry["embed-standard"]["target_url"] = "http://172.16.20.2:8012/v1"
    router._db_aliases = {"embed-standard"}

    async def _run():
        assert await router.resolve_target_url("embed-standard", "http://vllm-engine:8001/v1") == "http://172.16.20.2:8012/v1"
        assert await router.resolve_target_url("translate-vi-standard", "http://translation:8003/v1") == "http://translation:8003/v1"
        router._registry["embed-standard"]["status"] = "disabled"
        assert await router.resolve_target_url("embed-standard", "http://vllm-engine:8001/v1") is None

    asyncio.run(_run())


def _fake_request(headers):
    from starlette.requests import Request

    scope = {"type": "http", "method": "POST", "path": "/v1/rag/chat", "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()]}
    return Request(scope)


def test_gateway_key_identity_blocks_foreign_tenant_and_ignores_role_header():
    from src.auth.middleware import _apply_key_identity

    key = {"tenant_id": "tenant_a", "role": "user", "allowed_endpoints": ["*"]}

    req = _fake_request({"X-Tenant-ID": "tenant_b", "X-User-Role": "admin"})
    denied = _apply_key_identity(req, key, "aip_live_x", "req_1")
    assert denied is not None and denied.status_code == 403

    req = _fake_request({"X-User-Role": "admin"})
    assert _apply_key_identity(req, key, "aip_live_x", "req_2") is None
    assert (req.state.tenant_id, req.state.role) == ("tenant_a", "user")

    req = _fake_request({"X-Tenant-ID": "tenant_b"})
    assert _apply_key_identity(req, {**key, "allowed_tenants": ["tenant_b"]}, "aip_live_x", "req_3") is None
    assert req.state.tenant_id == "tenant_b"


def test_rag_identity_ignores_untrusted_headers(monkeypatch):
    from solutions.rag.interfaces.api import identity

    monkeypatch.delenv("TEST_MODE", raising=False)
    monkeypatch.setattr(identity.rag_settings, "trust_identity_headers", False)
    req = _fake_request({"X-Tenant-ID": "tenant_b", "X-User-Role": "admin"})
    assert identity.extract_tenant(req) == "proj_default"
    assert identity.extract_role(req) == "user"
    assert not identity.can_write_tenant(req, "proj_default")

    req.state.internal_caller = True
    assert identity.extract_tenant(req) == "tenant_b"
    assert identity.is_admin(req)
