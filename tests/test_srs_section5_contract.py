"""
Automated Contract & Verification Tests for SRS Section 5 (API Specifications).
Validates:
- 5.1: General structure, /v1/ prefix, /admin/v1/ prefix, headers (Authorization, X-Request-ID, Idempotency-Key)
- 5.2: All 14 Public Inference Endpoints contracts & methods
- 5.3: Standard Error Response Envelope format
"""

import io
import uuid
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient

from src.main import app

client = TestClient(app)
VALID_AUTH = {"Authorization": "Bearer aip_live_valid_test_key_12345"}


# =====================================================================
# Section 5.1: Headers & Structure
# =====================================================================
def test_srs5_1_idempotency_key_mandatory_for_jobs():
    """Verify that Idempotency-Key is MANDATORY for POST /v1/jobs (SRS 5.1)."""
    payload = {
        "job_type": "tasks.video",
        "alias_name": "video-wan2-standard",
        "payload": {"prompt": "A scenic view of Sapa mountains"},
    }

    # 1. Missing Idempotency-Key -> 400 validation_failed
    r_missing = client.post("/v1/jobs", json=payload, headers=VALID_AUTH)
    assert r_missing.status_code == 400
    data_missing = r_missing.json()
    assert "error" in data_missing
    err = data_missing["error"]
    assert err["type"] == "invalid_request_error"
    assert err["code"] == "validation_failed"
    assert "Idempotency-Key" in err["message"]
    assert err["retryable"] is False

    # 2. With Idempotency-Key -> 202 Accepted
    idemp_val = f"idemp_test_{uuid.uuid4().hex[:10]}"
    r_ok = client.post("/v1/jobs", json=payload, headers={**VALID_AUTH, "Idempotency-Key": idemp_val})
    assert r_ok.status_code == 202
    assert r_ok.json()["status"] == "queued"


def test_srs5_1_admin_endpoints_prefix():
    """Verify admin endpoints are prefixed with /admin/v1/ (SRS 5.1)."""
    resp = client.get("/admin/v1/endpoints")
    assert resp.status_code == 200
    assert "data" in resp.json()

    resp_aliases = client.get("/admin/v1/aliases")
    assert resp_aliases.status_code == 200


# =====================================================================
# Section 5.2: Verification of All 14 Public Inference Endpoints
# =====================================================================
def test_srs5_2_all_14_endpoints_exist_and_respond():
    """Verify all 14 inference endpoints defined in SRS 5.2 table exist with correct HTTP methods."""

    # 1. POST /v1/chat/completions
    mock_post_res = MagicMock()
    mock_post_res.status_code = 200
    mock_post_res.json.return_value = {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "created": 1770000000,
        "model": "chat-general-standard",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": "Xin chao"}}],
        "usage": {"prompt_tokens": 5, "completion_tokens": 5, "total_tokens": 10},
    }
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_p:
        mock_p.return_value = mock_post_res
        r1 = client.post("/v1/chat/completions", json={"model": "chat-general-standard", "messages": [{"role": "user", "content": "hi"}]}, headers=VALID_AUTH)
        assert r1.status_code == 200

    # 2. POST /v1/completions
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_p:
        mock_p.return_value = mock_post_res
        r2 = client.post("/v1/completions", json={"model": "chat-general-standard", "prompt": "Hi"}, headers=VALID_AUTH)
        assert r2.status_code in (200, 503)

    # 3. POST /v1/embeddings
    r3 = client.post("/v1/embeddings", json={"model": "embed-standard", "input": "Hello vector"}, headers=VALID_AUTH)
    assert r3.status_code in (200, 503)

    # 4. POST /v1/audio/transcriptions
    fake_wav = b"RIFF" + b"\x00" * 36 + b"WAVEfmt " + b"SPEECH_DATA"
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_p:
        mock_stt_res = MagicMock()
        mock_stt_res.status_code = 200
        mock_stt_res.json.return_value = {"text": "Xin chao", "language": "vi"}
        mock_stt_res.raise_for_status = MagicMock()
        mock_p.return_value = mock_stt_res
        r4 = client.post(
            "/v1/audio/transcriptions",
            files={"file": ("test.wav", io.BytesIO(fake_wav), "audio/wav")},
            data={"model": "stt-vn-standard", "language": "vi"},
            headers=VALID_AUTH,
        )
        assert r4.status_code == 200

    # 5. POST /v1/audio/speech
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_p:
        mock_tts_res = MagicMock()
        mock_tts_res.status_code = 200
        mock_tts_res.content = b"ID3\x03\x00\x00\x00"
        mock_tts_res.headers = {"content-type": "audio/mpeg"}
        mock_tts_res.raise_for_status = MagicMock()
        mock_p.return_value = mock_tts_res
        r5 = client.post(
            "/v1/audio/speech",
            json={"model": "tts-vn-standard", "input": "Xin chao"},
            headers=VALID_AUTH,
        )
        assert r5.status_code == 200

    # 6. POST /v1/images/generations
    r6 = client.post("/v1/images/generations", json={"prompt": "A dragon"}, headers=VALID_AUTH)
    assert r6.status_code in (200, 202)

    # 7. POST /v1/moderations
    r7 = client.post("/v1/moderations", json={"input": "An toan tuyet doi"}, headers=VALID_AUTH)
    assert r7.status_code == 200
    assert "results" in r7.json()

    # 8. POST /v1/predictions
    r8 = client.post("/v1/predictions", json={"alias_name": "translate-vi-standard", "payload": {"text": "Hello", "source_language": "en", "target_language": "vi"}}, headers=VALID_AUTH)
    assert r8.status_code == 200
    assert r8.json()["status"] == "success"

    # 9. POST /v1/jobs
    idemp_job = f"idemp_14_{uuid.uuid4().hex[:8]}"
    r9 = client.post("/v1/jobs", json={"job_type": "video", "alias_name": "video-wan2-standard", "payload": {"prompt": "test"}}, headers={**VALID_AUTH, "Idempotency-Key": idemp_job})
    assert r9.status_code == 202
    job_id = r9.json()["job_id"]

    # 10. GET /v1/jobs/{id}
    r10 = client.get(f"/v1/jobs/{job_id}", headers=VALID_AUTH)
    assert r10.status_code == 200
    assert r10.json()["job_id"] == job_id

    # 11. GET /v1/jobs/{id}/result
    r11 = client.get(f"/v1/jobs/{job_id}/result", headers=VALID_AUTH)
    assert r11.status_code == 200
    assert "result_urls" in r11.json()

    # 12. POST /v1/jobs/{id}/cancel
    r12 = client.post(f"/v1/jobs/{job_id}/cancel", headers=VALID_AUTH)
    assert r12.status_code == 200

    # 13. GET /v1/models
    r13 = client.get("/v1/models", headers=VALID_AUTH)
    assert r13.status_code == 200
    assert "data" in r13.json()

    # 14. GET /v1/models/{alias}
    r14 = client.get("/v1/models/chat-general-standard", headers=VALID_AUTH)
    assert r14.status_code == 200
    assert r14.json()["id"] == "chat-general-standard"


# =====================================================================
# Section 5.3: Error Response Format Verification
# =====================================================================
def test_srs5_3_error_envelope_schema():
    """Verify error envelope contains type, code, message, request_id, retryable (SRS 5.3)."""
    # 400 Bad Request
    resp = client.post("/v1/chat/completions", json={"invalid_field": True}, headers=VALID_AUTH)
    assert resp.status_code == 400
    body = resp.json()
    assert "error" in body
    err = body["error"]
    for field in ["type", "code", "message", "request_id", "retryable"]:
        assert field in err, f"Missing required error field '{field}' per SRS 5.3"
    assert isinstance(err["retryable"], bool)
    assert err["request_id"].startswith("req_")


def test_srs5_extended_features():
    """Verify extended Section 5 endpoints: /v1/ocr, /v1/images/edits, /v1/predictions/{alias}."""
    # 1. POST /v1/ocr direct endpoint
    fake_png = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4"
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_p:
        mock_ocr_res = MagicMock()
        mock_ocr_res.status_code = 200
        mock_ocr_res.json.return_value = {"text": "Document text", "confidence": 0.99}
        mock_ocr_res.raise_for_status = MagicMock()
        mock_p.return_value = mock_ocr_res

        r_ocr = client.post(
            "/v1/ocr",
            files={"file": ("test_doc.png", io.BytesIO(fake_png), "image/png")},
            headers=VALID_AUTH,
        )
        assert r_ocr.status_code == 200
        assert "text" in r_ocr.json()

    # 2. POST /v1/images/edits
    r_edits = client.post(
        "/v1/images/edits",
        files={"image": ("input.png", io.BytesIO(fake_png), "image/png")},
        data={"prompt": "Add sunglasses", "n": "1"},
        headers=VALID_AUTH,
    )
    assert r_edits.status_code == 200
    assert len(r_edits.json()["data"]) == 1
    assert "http" in r_edits.json()["data"][0]["url"]

    # 3. POST /v1/predictions/{alias}
    r_pred = client.post(
        "/v1/predictions/translate-vi-standard",
        json={"text": "How are you?", "source_language": "en", "target_language": "vi"},
        headers=VALID_AUTH,
    )
    assert r_pred.status_code == 200
    assert r_pred.json()["status"] == "success"
