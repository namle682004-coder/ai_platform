"""
Gateway -> standalone RAG service forwarding (platform/gateway/src/api/rag_proxy.py).

The gateway owns no RAG logic: it authenticates the caller, then forwards /v1/rag/* and
/v1/knowledge/* to the RAG service with the verified identity and the runtime token.
"""

import json

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from src.api import rag_proxy
from src.configs.settings import gateway_settings
from src.main import app

SANDBOX_KEY = "Bearer aip_live_valid_test_key_12345"


def _streamed(status_code, body, content_type="application/json"):
    """Upstream response with an unread body, as a real network response is (json=/content= are read eagerly)."""
    data = body if isinstance(body, bytes) else json.dumps(body).encode()

    async def chunks():
        yield data

    return httpx.Response(status_code, content=chunks(), headers={"content-type": content_type})


@pytest.fixture
def upstream(monkeypatch):
    """Replace the RAG service with an in-memory handler and record what it receives."""
    received = []
    responders = {}

    def handler(request: httpx.Request) -> httpx.Response:
        received.append(request)
        responder = responders.get(request.url.path)
        if responder:
            return responder(request)
        return _streamed(200, {"path": request.url.path})

    monkeypatch.setattr(gateway_settings, "rag_service_url", "http://rag-api:8010")
    monkeypatch.setattr(gateway_settings, "runtime_token", SecretStr("runtime-secret"))
    monkeypatch.setattr(rag_proxy, "_client", httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    return received, responders


def test_forwards_path_query_and_verified_identity(upstream):
    received, _ = upstream
    client = TestClient(app)

    res = client.get(
        "/v1/knowledge/documents?page=2&status=INDEXED",
        headers={
            "Authorization": SANDBOX_KEY,
            "X-Tenant-ID": "proj_alpha",
            "X-User-ID": "user_42",
            "X-AIP-Runtime-Token": "forged-by-client",
        },
    )

    assert res.status_code == 200
    assert res.json() == {"path": "/v1/knowledge/documents"}
    sent = received[0]
    assert str(sent.url) == "http://rag-api:8010/v1/knowledge/documents?page=2&status=INDEXED"
    assert sent.headers["X-Tenant-ID"] == "proj_alpha"
    assert sent.headers["X-User-ID"] == "user_42"
    assert sent.headers["Authorization"] == SANDBOX_KEY
    # The client's token is replaced by the gateway's own.
    assert sent.headers["X-AIP-Runtime-Token"] == "runtime-secret"


def test_forwards_body_and_upstream_status(upstream):
    received, responders = upstream
    responders["/v1/knowledge/qa"] = lambda req: _streamed(403, {"detail": "admin only"})
    client = TestClient(app)

    payload = {"question": "Giờ làm việc?", "answer": "8h-17h"}
    res = client.post("/v1/knowledge/qa", json=payload, headers={"Authorization": SANDBOX_KEY})

    assert res.status_code == 403
    assert res.json() == {"detail": "admin only"}
    assert json.loads(received[0].content) == payload
    assert received[0].method == "POST"


def test_streams_sse_chat(upstream):
    _, responders = upstream
    sse = b'data: {"delta": "Xin"}\n\ndata: {"delta": " chao"}\n\ndata: [DONE]\n\n'
    responders["/v1/rag/chat"] = lambda req: _streamed(200, sse, content_type="text/event-stream")
    client = TestClient(app)

    res = client.post(
        "/v1/rag/chat",
        json={"query": "xin chào", "stream": True},
        headers={"Authorization": SANDBOX_KEY},
    )

    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/event-stream")
    assert res.content == sse


def test_rag_service_down_returns_503(monkeypatch):
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    monkeypatch.setattr(rag_proxy, "_client", httpx.AsyncClient(transport=httpx.MockTransport(refuse)))
    client = TestClient(app)

    res = client.get("/v1/rag/sessions", headers={"Authorization": SANDBOX_KEY})

    assert res.status_code == 503
    assert res.json()["error"]["code"] == "rag_service_unavailable"


def test_requires_api_key(upstream):
    received, _ = upstream
    client = TestClient(app)

    res = client.get("/v1/knowledge/documents")

    assert res.status_code == 401
    assert received == []
