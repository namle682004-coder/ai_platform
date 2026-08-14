import hmac
import hashlib
import json
import httpx
from typing import Dict, Any


def sign_webhook_payload(payload: Dict[str, Any], secret: str) -> str:
    """
    Signs a Webhook JSON payload using HMAC-SHA256 as required by SRS Section 8.3.
    """
    serialized = json.dumps(payload, sort_keys=True).encode("utf-8")
    signature = hmac.new(secret.encode("utf-8"), serialized, hashlib.sha256).hexdigest()
    return f"sha256={signature}"


async def send_signed_webhook(webhook_url: str, payload: Dict[str, Any], secret: str) -> bool:
    """
    Sends a signed Webhook notification to downstream client with X-AIP-Signature header.
    """
    signature = sign_webhook_payload(payload, secret)
    headers = {
        "Content-Type": "application/json",
        "X-AIP-Signature": signature,
        "User-Agent": "AIP-Webhook-Notifier/1.0.0",
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.post(webhook_url, json=payload, headers=headers)
            return res.status_code < 400
    except Exception:
        return False
