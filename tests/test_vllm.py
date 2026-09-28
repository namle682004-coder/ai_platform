"""
Automated Unit & Contract Tests for Data-Plane vLLM Serving Engine.
Compliant with SRS Section 2.2, 3.4, 5.2, & 6.1.
"""

import importlib.util
import os
import sys

os.environ["TEST_MODE"] = "true"
from fastapi.testclient import TestClient

_server_dir = os.path.join(os.path.dirname(__file__), "..", "data-plane", "vllm-engine")
sys.path.insert(0, _server_dir)

_spec = importlib.util.spec_from_file_location("vllm_app_module", os.path.join(_server_dir, "app.py"))
_mod = importlib.util.module_from_spec(_spec)
sys.modules["vllm_app_module"] = _mod
_spec.loader.exec_module(_mod)
vllm_app = _mod.app

vllm_client = TestClient(vllm_app)


def test_vllm_health():
    """Verify vLLM serving engine health check endpoint."""
    response = vllm_client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "vllm-engine"
    assert "vLLM" in data["runtime"]
    assert "chat-general-standard" in data["models_served"]


def test_vllm_models_catalog():
    """Verify /v1/models returns OpenAI-compliant model list."""
    response = vllm_client.get("/v1/models")
    assert response.status_code == 200
    data = response.json()
    assert data["object"] == "list"
    models = {m["id"] for m in data["data"]}
    assert "chat-general-standard" in models
    assert "chat-general-high-quality" in models
    assert "summarize-high-quality" in models


def test_vllm_chat_completion_sync():
    """Verify non-streaming chat completion responds directly without meta notice."""
    payload = {
        "model": "chat-general-standard",
        "messages": [
            {"role": "user", "content": "hôm nay bạn khỏe k"}
        ],
        "temperature": 0.7,
        "stream": False,
    }
    response = vllm_client.post("/v1/chat/completions", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["object"] == "chat.completion"
    assert data["model"] == "chat-general-standard"
    assert len(data["choices"]) > 0
    reply = data["choices"][0]["message"]["content"]
    assert len(reply.strip()) > 0
    # Ensure NO sandbox notices
    assert "Môi trường Sandbox" not in reply
    assert "1. Bản chất vấn đề" not in reply


def test_vllm_chat_completion_streaming():
    """Verify streaming chat completion outputs valid OpenAI SSE format."""
    payload = {
        "model": "chat-general-standard",
        "messages": [
            {"role": "user", "content": "thủ đô của việt nam"}
        ],
        "temperature": 0.0,
        "stream": True,
    }
    response = vllm_client.post("/v1/chat/completions", json=payload)
    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]

    content_str = response.text
    assert "data: " in content_str
    assert "data: [DONE]" in content_str
    assert "chat.completion.chunk" in content_str


def test_vllm_text_completion():
    """Verify text completion endpoint (/v1/completions)."""
    payload = {
        "model": "chat-general-standard",
        "prompt": "Trí tuệ nhân tạo là",
        "max_tokens": 100,
    }
    response = vllm_client.post("/v1/completions", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["object"] == "text_completion"
    assert len(data["choices"]) > 0


def test_vllm_embeddings():
    """Verify vector embeddings endpoint (/v1/embeddings)."""
    payload = {
        "model": "embed-standard",
        "input": "Vector search with embeddings",
    }
    response = vllm_client.post("/v1/embeddings", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["object"] == "list"
    assert len(data["data"]) == 1
    assert len(data["data"][0]["embedding"]) in (1024, 1536)


def test_gateway_proxy_returns_503_when_vllm_offline():
    """Verify Control-Plane Gateway returns standard SRS 503 when vLLM node is unreachable."""
    from unittest.mock import AsyncMock, patch
    from src.main import app as gateway_app

    gw_client = TestClient(gateway_app)

    # Calling an unreachable port
    payload = {
        "model": "chat-general-standard",
        "messages": [{"role": "user", "content": "test connection failure"}],
        "stream": False,
    }
    headers = {"Authorization": "Bearer aip_live_valid_test_key_12345"}

    # Mock invalid target URL to trigger network error
    from src.items.alias_router import alias_router

    with patch.object(alias_router, "resolve_alias", new_callable=AsyncMock) as mock_resolve:
        mock_resolve.return_value = {
            "alias": "chat-general-standard",
            "runtime": "vLLM",
            "target_url": "http://127.0.0.1:59999/v1",  # Non-existent port
        }
        res = gw_client.post("/v1/chat/completions", json=payload, headers=headers)
        assert res.status_code == 503
        data = res.json()
        assert "error" in data
        assert data["error"]["code"] in ("runtime_unavailable", "service_unavailable")
        assert data["error"]["retryable"] is True
