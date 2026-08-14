from common.security.webhook_signer import sign_webhook_payload


def test_hmac_sha256_webhook_signing():
    payload = {"job_id": "job_01HXTEST", "status": "completed"}
    secret = "my_enterprise_webhook_secret"

    signature1 = sign_webhook_payload(payload, secret)
    signature2 = sign_webhook_payload(payload, secret)

    assert signature1.startswith("sha256=")
    assert signature1 == signature2
