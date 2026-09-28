"""
Automated tests for DCP-inspired Enterprise enhancements:
- SSRF NetGuard Egress Protection
- Redis-backed Idempotency Engine
- HMAC-SHA256 Webhook Signing & Anti-Tampering
"""

from fastapi.testclient import TestClient
from src.main import app
from common.security.netguard import is_safe_public_url
from common.security.webhook_signer import sign_webhook_payload, verify_webhook_signature

client = TestClient(app)
VALID_AUTH = {"Authorization": "Bearer aip_live_valid_test_key_12345"}


def test_netguard_blocks_ssrf_dangerous_targets():
    import asyncio
    async def _run():
        safe, reason = await is_safe_public_url("http://127.0.0.1:6379/keys")
        assert safe is False

        safe, reason = await is_safe_public_url("http://localhost:27017")
        assert safe is False

        safe, reason = await is_safe_public_url("http://169.254.169.254/latest/meta-data")
        assert safe is False

        safe, reason = await is_safe_public_url("http://10.0.0.5:8080/webhook")
        assert safe is False
    asyncio.run(_run())


def test_jobs_api_rejects_ssrf_webhook_url():
    res = client.post(
        "/v1/jobs",
        json={
            "job_type": "tasks.chat",
            "alias_name": "chat-general-standard",
            "payload": {"prompt": "test"},
            "webhook_url": "http://127.0.0.1:6379/hack",
        },
        headers={**VALID_AUTH, "Idempotency-Key": "idemp_ssrf_test_key_123"},
    )
    assert res.status_code == 400
    data = res.json()
    err_detail = data.get("error", {}).get("message") or data.get("detail", "")
    assert "SSRF Protection" in err_detail


def test_redis_idempotency_prevents_duplicate_jobs():
    idem_key = "idem_test_uuid_unique_9999"
    payload = {
        "job_type": "tasks.chat",
        "alias_name": "chat-general-standard",
        "payload": {"prompt": "test idempotency"},
    }

    res1 = client.post(
        "/v1/jobs",
        json=payload,
        headers={**VALID_AUTH, "Idempotency-Key": idem_key},
    )
    assert res1.status_code == 202
    job_id_1 = res1.json()["job_id"]

    res2 = client.post(
        "/v1/jobs",
        json=payload,
        headers={**VALID_AUTH, "Idempotency-Key": idem_key},
    )
    assert res2.status_code == 202
    job_id_2 = res2.json()["job_id"]

    assert job_id_1 == job_id_2


def test_webhook_hmac_signing_and_tampering_detection():
    secret = "my_enterprise_webhook_secret_key"
    payload = b'{"event":"job.completed","task_id":"job_123","status":"completed"}'

    import time
    now_ts = int(time.time())
    sig_header = sign_webhook_payload(payload, secret, timestamp=now_ts)
    assert "t=" in sig_header and "v1=" in sig_header

    valid, reason = verify_webhook_signature(payload, sig_header, secret)
    assert valid is True
    assert reason == ""

    tampered = b'{"event":"job.completed","task_id":"job_999_HACKED","status":"failed"}'
    valid, reason = verify_webhook_signature(tampered, sig_header, secret)
    assert valid is False
    assert "không khớp" in reason

    valid, reason = verify_webhook_signature(payload, sig_header, "wrong_secret")
    assert valid is False
