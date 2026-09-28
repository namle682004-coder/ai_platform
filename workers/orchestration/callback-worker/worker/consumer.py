"""
Dedicated Webhook Callback Consumer for AIP Platform.
Subscribes to q.aip.events.callbacks, enforces NetGuard SSRF security,
applies HMAC-SHA256 signature, and delivers callbacks with exponential backoff.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
import time
from typing import Optional

import aio_pika
import httpx
from aio_pika.abc import AbstractChannel, AbstractIncomingMessage, AbstractRobustConnection

from common.security.netguard import is_safe_public_url
from common.security.webhook_signer import sign_webhook_payload
from src.publisher.topology import QUEUE_CALLBACKS

logger = logging.getLogger("aip-callback.consumer")

DEFAULT_SECRET_KEY = "aip_webhook_secret_default_key_2026"
MAX_DELIVERY_ATTEMPTS = 3


class CallbackConsumer:
    """Consumes callback events and securely dispatches outbound webhooks."""

    def __init__(
        self,
        rabbitmq_url: str,
        secret_key: str = DEFAULT_SECRET_KEY,
        prefetch_count: int = 10,
    ):
        self.rabbitmq_url = rabbitmq_url
        self.secret_key = secret_key
        self.prefetch_count = prefetch_count
        self._connection: Optional[AbstractRobustConnection] = None
        self._channel: Optional[AbstractChannel] = None
        self._running: bool = False

    async def start(self) -> None:
        """Connect to RabbitMQ and listen on q.aip.events.callbacks."""
        self._connection = await aio_pika.connect_robust(self.rabbitmq_url)
        self._channel = await self._connection.channel()
        await self._channel.set_qos(prefetch_count=self.prefetch_count)

        queue = await self._channel.get_queue(QUEUE_CALLBACKS)
        await queue.consume(self._process_callback)
        self._running = True
        logger.info(
            "CallbackConsumer started — listening on %s (prefetch=%s)",
            QUEUE_CALLBACKS,
            self.prefetch_count,
        )

    async def stop(self) -> None:
        """Gracefully stop callback consumer."""
        self._running = False
        if self._channel and not self._channel.is_closed:
            await self._channel.close()
        if self._connection and not self._connection.is_closed:
            await self._connection.close()
        logger.info("CallbackConsumer stopped cleanly")

    async def _process_callback(self, message: AbstractIncomingMessage) -> None:
        """Process callback event with SSRF check, HMAC signature, and retry."""
        try:
            body = json.loads(message.body.decode("utf-8"))
        except Exception as exc:
            logger.error("Malformed callback message: %s", exc)
            await message.reject(requeue=False)
            return

        job_id = body.get("job_id", "unknown")
        webhook_url = body.get("webhook_url")
        event_type = body.get("event", "job.completed")

        if not webhook_url:
            logger.warning("Callback event for job %s has no webhook_url — skipping", job_id)
            await message.ack()
            return

        # 1. NetGuard SSRF Validation
        is_safe, error_reason = await is_safe_public_url(webhook_url)
        if not is_safe:
            logger.error(
                "SSRF violation blocked for job %s webhook target '%s': %s",
                job_id,
                webhook_url,
                error_reason,
            )
            # Unsafe URL -> drop without retry
            await message.reject(requeue=False)
            return

        # 2. Prepare Signed Payload
        delivery_id = f"del_{uuid.uuid4().hex[:12]}"
        now_ts = int(time.time())
        callback_payload = {
            "event": event_type,
            "job_id": job_id,
            "delivery_id": delivery_id,
            "timestamp": now_ts,
            "data": body,
        }
        payload_bytes = json.dumps(callback_payload, ensure_ascii=False).encode("utf-8")
        signature_hdr = sign_webhook_payload(payload_bytes, self.secret_key, timestamp=now_ts)

        headers = {
            "Content-Type": "application/json",
            "X-AIP-Signature": signature_hdr,
            "X-AIP-Event": event_type,
            "X-AIP-Delivery": delivery_id,
            "User-Agent": "AIP-Callback-Worker/1.0",
        }

        # 3. Deliver with Exponential Backoff Retry (1s, 2s, 4s)
        delivered = False
        async with httpx.AsyncClient(timeout=10.0) as client:
            for attempt in range(1, MAX_DELIVERY_ATTEMPTS + 1):
                try:
                    logger.info(
                        "Delivering webhook for job %s to %s (attempt %s/%s)...",
                        job_id, webhook_url, attempt, MAX_DELIVERY_ATTEMPTS,
                    )
                    res = await client.post(webhook_url, content=payload_bytes, headers=headers)
                    if 200 <= res.status_code < 300:
                        logger.info(
                            "✔ Webhook delivered successfully for job %s (status=%s, delivery_id=%s)",
                            job_id, res.status_code, delivery_id,
                        )
                        delivered = True
                        break
                    else:
                        logger.warning(
                            "Webhook target responded with status %s on attempt %s",
                            res.status_code, attempt,
                        )
                except Exception as exc:
                    logger.warning("Webhook delivery error on attempt %s: %s", attempt, exc)

                if attempt < MAX_DELIVERY_ATTEMPTS:
                    backoff_seconds = 2 ** (attempt - 1)
                    await asyncio.sleep(backoff_seconds)

        if delivered:
            await message.ack()
        else:
            logger.error(
                "Webhook delivery failed after %s attempts for job %s — sending to DLQ",
                MAX_DELIVERY_ATTEMPTS,
                job_id,
            )
            await message.reject(requeue=False)
