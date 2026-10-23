"""
Event Publisher for RAG Ingestion Worker.
Dispatches completion / failure events to AIP Callback exchange.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict

import aio_pika

logger = logging.getLogger("aip-rag.worker.publisher")

QUEUE_CALLBACKS = "q.aip.callbacks"


async def publish_callback_event(
    channel: aio_pika.abc.AbstractChannel,
    doc_id: str,
    status: str,
    details: Dict[str, Any],
) -> None:
    """Publish completion event to callbacks queue."""
    try:
        body = json.dumps({
            "event": "rag.document.indexed" if status == "completed" else "rag.document.failed",
            "doc_id": doc_id,
            "status": status,
            "details": details,
        }).encode()
        await channel.default_exchange.publish(
            aio_pika.Message(
                body=body,
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            ),
            routing_key=QUEUE_CALLBACKS,
        )
        logger.info("Published callback event for doc_id=%s status=%s", doc_id, status)
    except Exception as exc:
        logger.warning("Could not dispatch callback notification: %s", exc)
