"""Broker-Level Asynchronous Delayed Retry for AIP Dispatcher Worker.

Publishes failed tasks to the aip.retries delayed exchange with exponential backoff & full jitter.
Releases worker concurrency slots immediately (0ms blocking).
Compliant with DCP architectural principles.
"""

from __future__ import annotations

import json
import logging
import random

import aio_pika
from aio_pika import DeliveryMode, Message
from aio_pika.abc import AbstractChannel, AbstractExchange, AbstractRobustConnection

from common.messaging.topology import EXCHANGE_RETRIES, task_routing_key

logger = logging.getLogger("aip-dispatcher.retry")

MAX_RETRIES: int = 3
_BASE_DELAY_MS: int = 2_000   # 2 seconds base
_MAX_DELAY_MS: int = 60_000   # 60 seconds max


def compute_jittered_delay_ms(retry_count: int) -> int:
    exp_delay = min(_MAX_DELAY_MS, _BASE_DELAY_MS * (2 ** max(0, retry_count - 1)))
    return int(random.uniform(0.5 * exp_delay, exp_delay))


class RetryPublisher:
    """Publish retry messages to the aip.retries delayed exchange with x-delay."""

    def __init__(self, rabbitmq_url: str) -> None:
        self._rabbitmq_url = rabbitmq_url
        self._connection: AbstractRobustConnection | None = None
        self._channel: AbstractChannel | None = None
        self._exchange: AbstractExchange | None = None

    async def connect(self) -> None:
        if self._connection is not None and not self._connection.is_closed:
            return

        self._connection = await aio_pika.connect_robust(self._rabbitmq_url)
        self._channel = await self._connection.channel(publisher_confirms=True)
        self._exchange = await self._channel.declare_exchange(
            name=EXCHANGE_RETRIES,
            type="x-delayed-message",
            durable=True,
            passive=True,
        )
        logger.info("RetryPublisher connected and bound to %s", EXCHANGE_RETRIES)

    async def publish_retry(
        self,
        task_id: str,
        tenant_id: str,
        domain: str,
        priority: str,
        retry_count: int,
        failure_code: str,
        failure_message: str,
        alias_name: str | None = None,
    ) -> bool:
        if self._exchange is None or self._channel is None or self._connection is None or self._connection.is_closed:
            await self.connect()

        new_retry_count = retry_count + 1
        delay_ms = compute_jittered_delay_ms(new_retry_count)
        routing_key = task_routing_key(domain, priority)

        payload = {
            "schema_version": "1.0",
            "task_id": task_id,
            "tenant_id": tenant_id,
            "domain": domain,
            "priority": priority,
            "alias_name": alias_name,
            "retry_count": new_retry_count,
            "previous_failure": {
                "failure_code": failure_code,
                "failure_message": failure_message,
            },
        }

        body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        message = Message(
            body=body,
            delivery_mode=DeliveryMode.PERSISTENT,
            content_type="application/json",
            correlation_id=task_id,
            headers={"x-delay": delay_ms},
        )

        await self._exchange.publish(message=message, routing_key=routing_key)
        logger.info(
            "Task %s scheduled for retry %d/%d in %dms via %s (0ms blocking)",
            task_id, new_retry_count, MAX_RETRIES, delay_ms, EXCHANGE_RETRIES,
        )
        return True

    async def close(self) -> None:
        if self._channel and not self._channel.is_closed:
            await self._channel.close()
        if self._connection and not self._connection.is_closed:
            await self._connection.close()


__all__ = ["MAX_RETRIES", "RetryPublisher", "compute_jittered_delay_ms"]
