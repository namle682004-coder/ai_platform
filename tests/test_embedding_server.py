"""
API contract of platform/runtimes/embedding-server with the BGE models replaced by a fake
engine (FlagEmbedding/torch are only installed on the GPU host).
"""

import importlib
import importlib.util
import pathlib
import sys

import pytest
from fastapi.testclient import TestClient

_ROOT = pathlib.Path(__file__).resolve().parents[1] / "platform" / "runtimes" / "embedding-server"


def _load_app_module():
    name = "aip_embedding_server"
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, _ROOT / "__init__.py", submodule_search_locations=[str(_ROOT)])
        package = importlib.util.module_from_spec(spec)
        sys.modules[name] = package
        spec.loader.exec_module(package)
    return importlib.import_module(f"{name}.app")


class _FakeEngine:
    ready = True

    def load(self):
        pass

    def embed(self, texts, return_sparse=False):
        sparse = [{"indices": [7, 9], "values": [0.3, 0.1]} for _ in texts] if return_sparse else None
        return {"dense": [[0.5] * 4 for _ in texts], "sparse": sparse, "prompt_tokens": 3 * len(texts)}

    def rerank(self, query, documents):
        return [0.2, 0.9, 0.6][: len(documents)]

    def status(self):
        return {"status": "ready"}


@pytest.fixture
def client(monkeypatch):
    app_module = _load_app_module()
    monkeypatch.setattr(app_module, "engine", _FakeEngine())
    monkeypatch.setattr(app_module.settings, "runtime_token", "secret")
    monkeypatch.setattr(app_module.settings, "disable_auth", False)
    with TestClient(app_module.app) as c:
        yield c


def test_requires_runtime_token(client):
    assert client.post("/v1/embeddings", json={"input": "x"}).status_code == 401
    assert client.get("/health/ready").status_code == 200


def test_embeddings_openai_contract_with_optional_sparse(client):
    res = client.post(
        "/v1/embeddings",
        headers={"X-AIP-Runtime-Token": "secret"},
        json={"model": "embed-standard", "input": ["hóa đơn", "thuế"], "return_sparse": True},
    )
    assert res.status_code == 200
    body = res.json()
    assert [d["index"] for d in body["data"]] == [0, 1]
    assert len(body["data"][0]["embedding"]) == 4
    assert body["data"][0]["sparse"] == {"indices": [7, 9], "values": [0.3, 0.1]}
    assert body["usage"]["total_tokens"] == 6


def test_rerank_sorted_with_original_indices(client):
    res = client.post(
        "/v1/rerank",
        headers={"X-AIP-Runtime-Token": "secret"},
        json={"model": "rerank-standard", "query": "q", "documents": ["a", "b", "c"], "top_n": 2},
    )
    assert res.status_code == 200
    assert [(r["index"], r["relevance_score"]) for r in res.json()["results"]] == [(1, 0.9), (2, 0.6)]


def test_unknown_model_and_oversized_requests_are_rejected(client):
    headers = {"X-AIP-Runtime-Token": "secret"}
    assert client.post("/v1/embeddings", headers=headers, json={"model": "chat-general-standard", "input": "x"}).status_code == 404
    assert client.post("/v1/embeddings", headers=headers, json={"input": ["x"] * 1000}).status_code == 413
