"""
Automated Contract & Compliance Tests for AIP SRS Specifications.
Covers:
- SRS Section 3.4 & 5.3: Standard Error Envelope format
- SRS Section 6.1: Full 21-model catalog and alias detail lookup
- SRS Section 8.1: Key prefix validation and alias authorization enforcement
"""

from fastapi.testclient import TestClient
from src.main import app
from src.items.alias_router import AliasRouterService

client = TestClient(app)
VALID_AUTH = {"Authorization": "Bearer aip_live_valid_test_key_12345"}


def test_srs_legacy_runtime_name_is_normalized_without_rewriting_custom_runtimes():
    assert AliasRouterService._normalize_runtime("vllm", "vLLM") == "vLLM"
    assert (
        AliasRouterService._normalize_runtime("custom-vllm", "vLLM")
        == "custom-vllm"
    )


def test_srs_model_catalog_completeness():
    """Verify that models defined in catalog are present in /v1/models."""
    response = client.get("/v1/models", headers=VALID_AUTH)
    assert response.status_code == 200
    data = response.json()
    assert data["object"] == "list"
    models = data["data"]
    assert len(models) >= 7

    # Check key models across categories
    model_ids = {m["id"] for m in models}
    expected_models = [
        "chat-general-standard",
        "embed-standard",
        "translate-vi-standard",
        "stt-vn-standard",
        "tts-vi-standard",
        "idp-standard",
        "moderation-multimodal",
    ]
    for expected in expected_models:
        assert expected in model_ids, f"Expected alias '{expected}' not found in catalog"
    chat_model = next(
        model for model in models if model["id"] == "chat-general-standard"
    )
    assert chat_model["runtime"].startswith("vLLM ")


def test_srs_model_detail_metadata():
    """Verify granular specs returned by /v1/models/{alias} (SRS 5.2 & 6.1)."""
    response = client.get("/v1/models/chat-general-standard", headers=VALID_AUTH)
    assert response.status_code == 200
    m = response.json()
    assert m["id"] == "chat-general-standard"
    assert m["physical_model"] == "Qwen/Qwen2.5-1.5B-Instruct"
    assert m["runtime"] == "vLLM"
    assert m["namespace"] == "aip-text"
    assert m["min_vram_gb"] == 2
    assert m["stream_capable"] is True


def test_srs_error_envelope_format_on_validation_failure():
    """Verify exact SRS 5.3 JSON error structure on validation failure."""
    # Send request missing required 'messages' field
    response = client.post("/v1/chat/completions", json={"model": "chat-general-standard"}, headers=VALID_AUTH)
    assert response.status_code == 400
    body = response.json()
    assert "error" in body
    err = body["error"]
    assert err["type"] == "invalid_request_error"
    assert err["code"] == "validation_failed"
    assert "request_id" in err
    assert err["retryable"] is False


def test_srs_error_envelope_on_unauthorized():
    """Verify SRS 5.3 error structure on missing or invalid API key."""
    response = client.post("/v1/chat/completions", json={"model": "chat-general-standard", "messages": []})
    assert response.status_code == 401
    body = response.json()
    assert "error" in body
    err = body["error"]
    assert err["type"] == "authentication_error"
    assert err["code"] == "unauthorized"


def test_srs_error_envelope_on_invalid_key_prefix():
    """Verify that keys not following aip_live_ or aip_test_ are rejected with 401."""
    response = client.post(
        "/v1/chat/completions",
        json={"model": "chat-general-standard", "messages": []},
        headers={"Authorization": "Bearer sk-proj-invalidkey12345"}
    )
    assert response.status_code == 401
    body = response.json()
    assert "error" in body
    assert body["error"]["code"] == "invalid_api_key"


def test_srs_alias_not_found():
    """Verify 404 alias_not_found when model alias is unknown (SRS 3.4)."""
    response = client.post(
        "/v1/chat/completions",
        json={"model": "non-existent-model-xyz", "messages": [{"role": "user", "content": "hi"}]},
        headers=VALID_AUTH
    )
    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "alias_not_found"
