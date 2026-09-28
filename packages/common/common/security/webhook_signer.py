"""
Webhook HMAC-SHA256 Signing & Verification for AIP Platform.
Inspired by DCP Webhook Signing architecture.

Ensures authenticity and integrity of outbound webhook deliveries so clients
can verify that callbacks genuinely originated from the AIP platform and
have not been tampered with in transit.
"""

from __future__ import annotations

import hmac
import hashlib
import json
import time
from typing import Any


def _to_bytes(payload: dict[str, Any] | str | bytes) -> bytes:
    if isinstance(payload, bytes):
        return payload
    if isinstance(payload, str):
        return payload.encode("utf-8")
    return json.dumps(payload, sort_keys=True).encode("utf-8")


def sign_webhook_payload(
    payload: dict[str, Any] | str | bytes,
    secret_key: str,
    timestamp: int | None = None,
) -> str:
    """
    Generate an HMAC-SHA256 signature header string for a webhook payload.

    If timestamp is provided, returns:
        t={timestamp},v1={hex_signature} (DCP standard format)
    If timestamp is None, returns:
        sha256={hex_signature} (Standard GitHub/Stripe format)
    """
    payload_bytes = _to_bytes(payload)

    if timestamp is not None:
        signed_payload = f"{timestamp}.".encode("utf-8") + payload_bytes
        signature = hmac.new(
            secret_key.encode("utf-8"),
            signed_payload,
            hashlib.sha256,
        ).hexdigest()
        return f"t={timestamp},v1={signature}"

    signature = hmac.new(
        secret_key.encode("utf-8"),
        payload_bytes,
        hashlib.sha256,
    ).hexdigest()
    return f"sha256={signature}"


def verify_webhook_signature(
    payload: dict[str, Any] | str | bytes,
    signature_header: str,
    secret_key: str,
    tolerance_seconds: int = 300,
) -> tuple[bool, str]:
    """
    Verify an incoming webhook signature against payload and secret key.
    Supports both 't=...,v1=...' and 'sha256=...' signature formats.

    Returns:
        tuple[bool, str]: (is_valid, reason)
    """
    if not signature_header:
        return False, "Thiếu header chữ ký Webhook"

    payload_bytes = _to_bytes(payload)

    # Format 1: Standard 'sha256=...' format
    if signature_header.startswith("sha256="):
        expected_sig = f"sha256={hmac.new(secret_key.encode('utf-8'), payload_bytes, hashlib.sha256).hexdigest()}"
        if hmac.compare_digest(expected_sig, signature_header):
            return True, ""
        return False, "Chữ ký số HMAC-SHA256 không khớp"

    # Format 2: DCP timestamped 't=...,v1=...' format
    parts = dict(
        item.strip().split("=", 1)
        for item in signature_header.split(",")
        if "=" in item
    )

    ts_str = parts.get("t")
    v1_sig = parts.get("v1")

    if not ts_str or not v1_sig:
        return False, "Định dạng header chữ ký không hợp lệ"

    try:
        ts = int(ts_str)
    except ValueError:
        return False, "Timestamp trong chữ ký không hợp lệ"

    # Anti-replay attack check
    current_time = int(time.time())
    if abs(current_time - ts) > tolerance_seconds:
        return False, f"Chữ ký đã hết hạn (chênh lệch {abs(current_time - ts)}s > {tolerance_seconds}s)"

    signed_payload = f"{ts}.".encode("utf-8") + payload_bytes
    expected_sig = hmac.new(
        secret_key.encode("utf-8"),
        signed_payload,
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected_sig, v1_sig):
        return False, "Chữ ký số HMAC-SHA256 không khớp"

    return True, ""
