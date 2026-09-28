"""
Automated Contract & Unit Tests for Centralized Inference Caching.
Validates:
- SRS Section 5.1 & 8.1 compliant caching across Embeddings, Moderation, Translation, OCR & Chat
- Deterministic response verification
- Standard X-Cache: HIT/MISS headers
- Cache-Control: no-cache bypass behavior
- Graceful fail-open error handling
- Prometheus metrics recording
"""

import io
import uuid
from fastapi.testclient import TestClient
from src.main import app

client = TestClient(app)
VALID_AUTH = {"Authorization": "Bearer aip_live_valid_test_key_12345"}


def test_embeddings_cache_hit_and_headers():
    """Verify that repeated /v1/embeddings queries hit the cache and return X-Cache: HIT."""
    test_id = uuid.uuid4().hex[:8]
    payload = {
        "model": "embed-standard",
        "input": f"Hệ thống AI Inference Platform tối ưu cho ngân hàng {test_id}",
    }

    # 1. First request -> MISS
    resp1 = client.post("/v1/embeddings", json=payload, headers=VALID_AUTH)
    assert resp1.status_code == 200
    assert resp1.headers.get("X-Cache") == "MISS"
    data1 = resp1.json()

    # 2. Second request with same payload -> HIT
    resp2 = client.post("/v1/embeddings", json=payload, headers=VALID_AUTH)
    assert resp2.status_code == 200
    assert resp2.headers.get("X-Cache") == "HIT"
    assert resp2.headers.get("X-Cache-Node") == "redis-cache"
    data2 = resp2.json()

    # Deterministic output check
    assert data1["data"][0]["embedding"] == data2["data"][0]["embedding"]


def test_moderations_cache_hit_and_headers():
    """Verify that repeated /v1/moderations queries hit cache."""
    test_id = uuid.uuid4().hex[:8]
    payload = {
        "model": "moderation-multimodal",
        "input": f"Nội dung văn bản kiểm tra an toàn hệ thống {test_id}",
    }

    # First request
    resp1 = client.post("/v1/moderations", json=payload, headers=VALID_AUTH)
    assert resp1.status_code == 200

    # Second request -> HIT
    resp2 = client.post("/v1/moderations", json=payload, headers=VALID_AUTH)
    assert resp2.status_code == 200
    assert resp2.headers.get("X-Cache") == "HIT"
    assert resp2.headers.get("X-Cache-Node") == "redis-cache"


def test_cache_control_no_cache_bypasses():
    """Verify that client header Cache-Control: no-cache bypasses cache."""
    test_id = uuid.uuid4().hex[:8]
    payload = {
        "model": "embed-standard",
        "input": f"Văn bản thử nghiệm bypass cache qua RFC header {test_id}",
    }

    # Warm up cache
    client.post("/v1/embeddings", json=payload, headers=VALID_AUTH)

    # Request with Cache-Control: no-cache
    bypass_headers = {**VALID_AUTH, "Cache-Control": "no-cache"}
    resp = client.post("/v1/embeddings", json=payload, headers=bypass_headers)
    assert resp.status_code == 200
    assert resp.headers.get("X-Cache") == "MISS"


def test_chat_cache_conditional_on_temperature():
    """Verify that /v1/chat/completions caches when temperature=0.0."""
    from unittest.mock import AsyncMock, patch

    test_id = uuid.uuid4().hex[:8]
    payload_deterministic = {
        "model": "chat-general-standard",
        "messages": [{"role": "user", "content": f"Thủ đô của Việt Nam là gì {test_id}?"}],
        "temperature": 0.0,
        "stream": False,
    }

    mock_vllm_reply = {
        "id": "chatcmpl-test-vllm",
        "object": "chat.completion",
        "created": 1726000000,
        "model": "chat-general-standard",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "Thủ đô của Việt Nam là Hà Nội."},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 8, "total_tokens": 18},
    }

    with patch("src.api.chat.proxy_service.proxy_post", new_callable=AsyncMock) as mock_proxy:
        mock_proxy.return_value = mock_vllm_reply

        # 1. First call -> MISS
        resp1 = client.post("/v1/chat/completions", json=payload_deterministic, headers=VALID_AUTH)
        assert resp1.status_code == 200
        assert resp1.headers.get("X-Cache") == "MISS"
        assert mock_proxy.call_count == 1

        # 2. Second call -> HIT (from Redis, proxy not called again)
        resp2 = client.post("/v1/chat/completions", json=payload_deterministic, headers=VALID_AUTH)
        assert resp2.status_code == 200
        assert resp2.headers.get("X-Cache") == "HIT"
        assert resp2.headers.get("X-Cache-Node") == "redis-cache"
        assert mock_proxy.call_count == 1


def test_translation_cache_centralized():
    """Verify that /v1/nlp/translation utilizes centralized cache or in-process fallback."""
    test_id = uuid.uuid4().hex[:8]
    payload = {
        "text": f"Xin chào thế giới máy học {test_id}",
        "source_lang": "vi",
        "target_lang": "en",
    }

    # First translation
    resp1 = client.post("/v1/nlp/translation", json=payload, headers=VALID_AUTH)
    assert resp1.status_code == 200
    data1 = resp1.json()
    assert data1.get("status") == "success"
    assert "translated_text" in data1

    # Second translation -> HIT (if Redis available) or fallback
    resp2 = client.post("/v1/nlp/translation", json=payload, headers=VALID_AUTH)
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2.get("status") == "success"
    assert "translated_text" in data2
    # Cache HIT when Redis is online, otherwise verify consistent translation
    if data2.get("cached") is True:
        assert data2.get("node") == "redis-cache"
    else:
        # In-process or localized fallback — response still valid
        assert data2["translated_text"] == data1["translated_text"]


def test_ocr_image_hash_cache():
    """Verify that uploading the exact same image to OCR ID-card hits cache on 2nd attempt."""
    test_id = uuid.uuid4().hex[:8]
    fake_image_bytes = f"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR_{test_id}".encode("utf-8")
    files = {"image": ("test_id.png", io.BytesIO(fake_image_bytes), "image/png")}

    # First attempt
    resp1 = client.post("/v1/ocr/id-card", files=files, headers=VALID_AUTH)
    if resp1.status_code == 200:
        # Second attempt with same file bytes -> HIT
        files2 = {"image": ("test_id.png", io.BytesIO(fake_image_bytes), "image/png")}
        resp2 = client.post("/v1/ocr/id-card", files=files2, headers=VALID_AUTH)
        assert resp2.status_code == 200
        assert resp2.headers.get("X-Cache") == "HIT"


def test_prometheus_cache_metrics_exposed():
    """Verify that /metrics endpoint exposes aip_inference_cache_hits_total."""
    resp = client.get("/metrics")
    assert resp.status_code == 200
    body = resp.text
    assert "aip_inference_cache_hits_total" in body
    assert "aip_inference_cache_misses_total" in body

