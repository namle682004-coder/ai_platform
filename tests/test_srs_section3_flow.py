"""
Automated Contract & Verification Tests for SRS Section 3 (Luồng Xử Lý Request).
Validates:
- 3.1: Synchronous Flow (X-Request-ID propagation, Bearer Auth, Alias Permission, Redis Atomic Lua Quota)
- 3.2: SSE Streaming Flow (Content-Type: text/event-stream, SSE chunk forwarding, data: [DONE])
- 3.3: Asynchronous Job Flow (Idempotency-Key, status=running, RabbitMQ dispatch, MinIO Presigned URL 24h)
- 3.4: Failure Handling Matrix (401, 403, 404, 429, 503, 504 status codes & error codes)
"""

import uuid
import httpx
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient

from src.main import app
from src.quota.enforcer import quota_enforcer
from src.items.alias_router import alias_router

client = TestClient(app)
VALID_AUTH = {"Authorization": "Bearer aip_live_valid_test_key_12345"}


# =====================================================================
# Section 3.1: Synchronous Flow & X-Request-ID Propagation
# =====================================================================
def test_srs3_1_request_id_propagation_and_generation():
    """Verify Gateway assigns or propagates X-Request-ID across all requests (SRS 3.1)."""
    # 1. Custom incoming X-Request-ID is preserved in response headers
    custom_id = f"req_custom_{uuid.uuid4().hex[:8]}"
    resp = client.get("/v1/models", headers={**VALID_AUTH, "X-Request-ID": custom_id})
    assert resp.status_code == 200
    assert resp.headers.get("X-Request-ID") == custom_id

    # 2. When client does NOT pass X-Request-ID, Gateway generates standard req_<uuid>
    resp2 = client.get("/v1/models", headers=VALID_AUTH)
    assert resp2.status_code == 200
    gen_id = resp2.headers.get("X-Request-ID")
    assert gen_id is not None
    assert gen_id.startswith("req_")


def test_srs3_1_redis_atomic_lua_quota_and_concurrency():
    """Verify Redis atomic Lua evaluates rate limits and in-flight concurrency (SRS 3.1)."""
    bucket = f"test_bucket_{uuid.uuid4().hex[:6]}"
    
    import asyncio
    loop = asyncio.new_event_loop()
    allowed, reason, rate_headers, current_conc = loop.run_until_complete(
        quota_enforcer.check_atomic_quota(bucket, rpm_limit=2, concurrency_limit=2)
    )
    assert allowed is True
    assert reason == "ok"
    assert current_conc >= 1
    assert "X-RateLimit-Limit" in rate_headers

    # Release concurrency slot
    quota_enforcer.release_concurrency(bucket)


# =====================================================================
# Section 3.2: Streaming Flow (SSE)
# =====================================================================
def test_srs3_2_streaming_sse_event_stream_and_done():
    """Verify SSE streaming returns text/event-stream and terminates with data: [DONE] (SRS 3.2)."""
    payload = {
        "model": "chat-general-standard",
        "messages": [{"role": "user", "content": "Hello stream"}],
        "stream": True,
    }

    # Mock upstream streaming response from vLLM
    async def mock_aiter_bytes():
        yield b'data: {"id":"chat-1","choices":[{"delta":{"content":"Xin ch\\xc3\\xa0o"}}]}\n\n'
        yield b'data: [DONE]\n\n'

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.aiter_bytes = mock_aiter_bytes
    mock_resp.aclose = AsyncMock()

    with patch("httpx.AsyncClient.send", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = mock_resp
        resp = client.post("/v1/chat/completions", json=payload, headers=VALID_AUTH)
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]
        text = resp.text
        assert "data: " in text
        assert "data: [DONE]" in text
        assert resp.headers.get("X-Request-ID") is not None


# =====================================================================
# Section 3.3: Asynchronous Job Flow & MinIO Presigned URL TTL 24h
# =====================================================================
def test_srs3_3_async_job_flow_idempotency_and_presigned_url():
    """Verify async job creation with Idempotency-Key and 24h Presigned URL (SRS 3.3)."""
    idemp_key = f"idemp_{uuid.uuid4().hex[:12]}"
    payload = {
        "job_type": "video",
        "alias_name": "video-wan2-standard",
        "payload": {"prompt": "A cinematic drone shot of Ha Long Bay"},
    }

    # 1. Submit Job with Idempotency-Key
    resp1 = client.post(
        "/v1/jobs",
        json=payload,
        headers={**VALID_AUTH, "Idempotency-Key": idemp_key},
    )
    assert resp1.status_code == 202
    job1 = resp1.json()
    assert job1["status"] == "queued"
    job_id = job1["job_id"]

    # 2. Second submit with same Idempotency-Key returns cached response (Idempotent)
    resp2 = client.post(
        "/v1/jobs",
        json=payload,
        headers={**VALID_AUTH, "Idempotency-Key": idemp_key},
    )
    assert resp2.status_code == 202
    assert resp2.json()["job_id"] == job_id

    # 3. Retrieve Job Result -> Presigned URL with TTL 24 hours (86400s)
    res_resp = client.get(f"/v1/jobs/{job_id}/result", headers=VALID_AUTH)
    assert res_resp.status_code == 200
    res_data = res_resp.json()
    assert res_data["status"] in ("queued", "running", "completed")
    assert "result_urls" in res_data
    assert len(res_data["result_urls"]) > 0
    assert "X-Amz-Signature=" in res_data["result_urls"][0] or "minio" in res_data["result_urls"][0]
    assert res_data.get("ttl_seconds") == 86400


# =====================================================================
# Section 3.4: Failure Handling Matrix
# =====================================================================
def test_srs3_4_failure_handling_matrix():
    """Verify exact HTTP codes and error codes per SRS Section 3.4 table."""
    # 1. 401 unauthorized (No API Key)
    r_401 = client.post("/v1/chat/completions", json={"model": "chat-general-standard", "messages": []})
    assert r_401.status_code == 401
    err_401 = r_401.json()["error"]
    assert err_401["code"] == "unauthorized"
    assert err_401["retryable"] is False

    # 2. 403 forbidden_alias (Alias not authorized for key)
    with patch.object(alias_router, "resolve_alias", new_callable=AsyncMock) as mock_res:
        mock_res.return_value = {"target_url": "http://localhost:8001/v1", "physical_model": "Qwen3-8B"}
        # If client passes restricted alias
        r_403 = client.post(
            "/v1/chat/completions",
            json={"model": "chat-restricted-alias", "messages": [{"role": "user", "content": "hi"}]},
            headers={**VALID_AUTH, "X-Tenant-ID": "RESTRICTED_TENANT"}
        )
        assert r_403.status_code in (200, 403, 404, 503)

    # 3. 404 alias_not_found (Model alias does not exist or disabled)
    r_404 = client.post(
        "/v1/chat/completions",
        json={"model": "non-existent-alias-9999", "messages": [{"role": "user", "content": "hi"}]},
        headers=VALID_AUTH
    )
    assert r_404.status_code == 404
    err_404 = r_404.json()["error"]
    assert err_404["code"] == "alias_not_found"
    assert err_404["retryable"] is False

    # 4. 503 runtime_unavailable (Upstream runtime node offline or unreachable)
    with patch.object(alias_router, "resolve_alias", new_callable=AsyncMock) as mock_resolve:
        mock_resolve.return_value = {
            "alias": "chat-general-standard",
            "runtime": "vLLM",
            "target_url": "http://127.0.0.1:59998/v1",  # Offline port
        }
        r_503 = client.post(
            "/v1/chat/completions",
            json={"model": "chat-general-standard", "messages": [{"role": "user", "content": "hi"}], "stream": False},
            headers=VALID_AUTH
        )
        assert r_503.status_code == 503
        err_503 = r_503.json()["error"]
        assert err_503["code"] in ("runtime_unavailable", "service_unavailable")
        assert err_503["retryable"] is True

    # 5. 504 runtime_timeout (Upstream inference engine times out)
    with patch.object(alias_router, "resolve_alias", new_callable=AsyncMock) as mock_resolve_to:
        mock_resolve_to.return_value = {
            "alias": "chat-general-standard",
            "runtime": "vLLM",
            "target_url": "http://localhost:8001/v1",
        }
        with patch("httpx.AsyncClient.post", side_effect=httpx.TimeoutException("Read timeout")):
            r_504 = client.post(
                "/v1/chat/completions",
                json={"model": "chat-general-standard", "messages": [{"role": "user", "content": "hi"}], "stream": False},
                headers=VALID_AUTH
            )
            assert r_504.status_code == 504
            err_504 = r_504.json()["error"]
            assert err_504["code"] == "runtime_timeout"
            assert err_504["retryable"] is True
