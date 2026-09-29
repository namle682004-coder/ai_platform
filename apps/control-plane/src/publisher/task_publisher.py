"""
RabbitMQ task publisher for AIP Control Plane task dispatch.

Publishes task messages to the ``aip.tasks`` topic exchange using
domain-based routing keys: ``aip.tasks.{domain}.{priority}``.

Features:
- Native RabbitMQ AMQP message priority (0-10):
    * high   -> 9 (or 10)
    * normal -> 5
    * batch  -> 1
- Auto-resolves domain from alias_name (e.g. 'stt-vn-standard' -> 'stt')
  or task_type (e.g. 'tasks.chat' -> 'chat', 'tasks.stt' -> 'stt').
- Supports custom tasks outside the model catalog.
- Lazy-connects on first publish if not already connected.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional, Union

import aio_pika
from aio_pika import DeliveryMode, Message
from aio_pika.abc import (
    AbstractChannel,
    AbstractExchange,
    AbstractRobustConnection,
)

from src.publisher.topology import (
    EXCHANGE_TASKS,
    PRIORITIES,
    resolve_task_domain,
)

logger = logging.getLogger("aip-messaging.publisher")
_SCHEMA_VERSION = "1.0"


class TaskPublisherError(RuntimeError):
    """Base error for task publisher failures."""


class TaskPublisherNotConnectedError(TaskPublisherError):
    """Raised when publish is attempted without an active connection."""


class TaskPublishError(TaskPublisherError):
    """Raised when RabbitMQ fails to accept a task publication."""


class TaskPublisher:
    """Publish task dispatch messages to RabbitMQ with confirms."""

    def __init__(self, rabbitmq_url: str) -> None:
        if not isinstance(rabbitmq_url, str) or not rabbitmq_url.strip():
            raise TaskPublisherError("rabbitmq_url must be a non-empty string")

        self._rabbitmq_url = rabbitmq_url
        self._connection: AbstractRobustConnection | None = None
        self._channel: AbstractChannel | None = None
        self._exchange: AbstractExchange | None = None

    async def connect(self) -> None:
        """Create robust RabbitMQ connection/channel and bind to task exchange."""
        if self._connection is not None and not self._connection.is_closed:
            return

        try:
            self._connection = await aio_pika.connect_robust(self._rabbitmq_url)
            self._channel = await self._connection.channel(publisher_confirms=True)
            self._exchange = await self._channel.declare_exchange(
                name=EXCHANGE_TASKS,
                type=aio_pika.ExchangeType.TOPIC,
                durable=True,
                passive=True,
            )
            logger.info("TaskPublisher connected and bound to '%s'", EXCHANGE_TASKS)
        except Exception as exc:
            await self.close()
            raise TaskPublisherError(f"Failed to connect publisher to RabbitMQ: {exc}") from exc

    async def publish_task(
        self,
        task_id: str,
        tenant_id: str,
        task_type: str,
        priority: Union[str, int] = "normal",
        payload: dict[str, Any] | None = None,
        alias_name: Optional[str] = None,
        domain: Optional[str] = None,
    ) -> bool:
        """
        Publish a task dispatch message and wait for broker confirmation.

        Parameters
        ----------
        task_id : str
            Unique job identifier (becomes ``correlation_id``).
        tenant_id : str
            Tenant / API-key owner.
        task_type : str
            Logical task type (e.g. ``tasks.chat``, ``tasks.stt``, ``video_generation``, or custom).
        priority : str or int
            One of ``high``, ``normal``, ``batch`` or int (0-10).
        payload : dict | None
            Arbitrary JSON-serialisable task data.
        alias_name : str | None
            Model alias (e.g. 'stt-vn-standard', 'chat-general-standard').
            If provided, used to automatically resolve domain!
        domain : str | None
            Explicit domain override. If None, auto-resolved from alias_name & task_type.
        """
        # Lazy connect on demand when publishing if connection was not established
        if self._exchange is None or self._channel is None or self._connection is None or self._connection.is_closed:
            await self.connect()

        # Map priority string/int to AMQP message priority integer (0-10)
        priority_int_map = {"high": 9, "normal": 5, "batch": 1}
        if isinstance(priority, int):
            priority_num = max(0, min(10, priority))
            priority_str = "high" if priority_num >= 8 else ("batch" if priority_num <= 2 else "normal")
        else:
            priority_str = str(priority).lower()
            if priority_str not in PRIORITIES:
                priority_str = "normal"
            priority_num = priority_int_map.get(priority_str, 5)

        # Intelligently resolve domain from alias_name or task_type
        if not domain:
            domain = resolve_task_domain(alias_name=alias_name, task_type=task_type)

        routing_key = f"aip.tasks.{domain}.{priority_str}"
        msg_payload: dict[str, Any] = {
            "schema_version": _SCHEMA_VERSION,
            "task_id": task_id,
            "tenant_id": tenant_id,
            "alias_name": alias_name,
            "task_type": task_type,
            "domain": domain,
            "priority": priority_str,
            "priority_level": priority_num,
            "submitted_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "data": payload or {},
        }

        body = json.dumps(msg_payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        message = Message(
            body=body,
            delivery_mode=DeliveryMode.PERSISTENT,
            content_type="application/json",
            correlation_id=task_id,
            priority=priority_num,
        )

        try:
            confirmation = await self._exchange.publish(message=message, routing_key=routing_key)
        except Exception as exc:
            raise TaskPublishError(
                f"Failed to publish task '{task_id}' to routing key '{routing_key}': {exc}"
            ) from exc

        confirmation_name = type(confirmation).__name__.lower() if confirmation is not None else ""
        if "nack" in confirmation_name or "reject" in confirmation_name:
            raise TaskPublishError(
                f"Broker did not acknowledge task '{task_id}' for routing key '{routing_key}'"
            )

        logger.info(
            "Task published successfully",
            extra={
                "task_id": task_id,
                "domain": domain,
                "priority": priority_str,
                "priority_num": priority_num,
                "routing_key": routing_key,
                "alias_name": alias_name,
            },
        )
        return True

    async def close(self) -> None:
        """Close publisher channel and connection cleanly."""
        if self._channel is not None and not self._channel.is_closed:
            await self._channel.close()
        self._channel = None
        self._exchange = None

        if self._connection is not None and not self._connection.is_closed:
            await self._connection.close()
        self._connection = None


__all__ = [
    "TaskPublishError",
    "TaskPublisher",
    "TaskPublisherError",
    "TaskPublisherNotConnectedError",
]
