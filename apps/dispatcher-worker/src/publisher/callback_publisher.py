"""
AIP Callback Event Publisher for Dispatcher Worker.
Publishes persistent terminal state events to RabbitMQ `aip.events` exchange.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

import aio_pika
from aio_pika.abc import AbstractChannel

logger = logging.getLogger("aip-dispatcher.publisher")

EXCHANGE_EVENTS = "aip.events"


class CallbackPublisher:
    """Publishes completion/failure events for Callback-Worker to process."""

    async def publish_event(
        self,
        channel: AbstractChannel,
        job_id: str,
        domain: str,
        status: str,
        webhook_url: Optional[str],
        duration_ms: int,
        result: dict[str, Any],
        error_message: Optional[str] = None,
        completed_at: Optional[str] = None,
    ) -> bool:
        """Publishes event to aip.events exchange with PERSISTENT delivery mode."""
        if not webhook_url:
            return False

        try:
            events_exchange = await channel.get_exchange(EXCHANGE_EVENTS)
            event_body = {
                "event": f"job.{status}",
                "job_id": job_id,
                "domain": domain,
                "status": status,
                "webhook_url": webhook_url,
                "duration_ms": duration_ms,
                "result": result,
                "error_message": error_message,
                "completed_at": completed_at,
            }
            msg = aio_pika.Message(
                body=json.dumps(event_body, ensure_ascii=False).encode("utf-8"),
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                content_type="application/json",
            )
            await events_exchange.publish(
                msg,
                routing_key=f"aip.events.job.{status}",
            )
            logger.info("Published callback event for job %s to %s", job_id, EXCHANGE_EVENTS)
            return True
        except Exception as exc:
            logger.warning("Failed to publish callback event for %s: %s", job_id, exc)
            return False


callback_publisher = CallbackPublisher()
