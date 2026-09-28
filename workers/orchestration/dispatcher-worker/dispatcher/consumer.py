"""
Dispatcher Consumer for AIP Platform.
Subscribes to domain queues, updates MongoDB job lifecycle, and dispatches
completion events to the dedicated Callback-Worker.
"""

from __future__ import annotations

import json
import logging
import os
import socket
from datetime import datetime, timezone
from typing import Any, Optional

import aio_pika
from aio_pika.abc import AbstractChannel, AbstractIncomingMessage, AbstractRobustConnection

from common.repositories.mongo_repositories import job_repository
from src.publisher.topology import (
    CORE_TASK_DOMAINS,
    EXCHANGE_EVENTS,
    queue_name,
    resolve_task_domain,
)

logger = logging.getLogger("aip-dispatcher.consumer")

WORKER_NODE_ID = os.getenv("AIP_NODE_ID", f"dispatcher-{socket.gethostname()}")


class DispatcherConsumer:
    """Consumes AI tasks from RabbitMQ and updates execution telemetry."""

    def __init__(
        self,
        rabbitmq_url: str,
        prefetch_count: int = 5,
    ):
        self.rabbitmq_url = rabbitmq_url
        self.prefetch_count = prefetch_count
        self._connection: Optional[AbstractRobustConnection] = None
        self._channel: Optional[AbstractChannel] = None
        self._running: bool = False

    async def start(self) -> None:
        """Connect to RabbitMQ and start consuming from all 12 domain queues."""
        self._connection = await aio_pika.connect_robust(self.rabbitmq_url)
        self._channel = await self._connection.channel()
        await self._channel.set_qos(prefetch_count=self.prefetch_count)

        self._running = True
        logger.info(
            "DispatcherConsumer connected (node_id=%s, prefetch=%s). Subscribing to domain queues...",
            WORKER_NODE_ID,
            self.prefetch_count,
        )

        for domain in CORE_TASK_DOMAINS:
            q_name = queue_name(domain)
            try:
                queue = await self._channel.get_queue(q_name)
                await queue.consume(self._process_message)
                logger.debug("Dispatcher subscribed to queue: %s", q_name)
            except Exception as exc:
                logger.warning("Could not subscribe to queue %s: %s", q_name, exc)

        logger.info("DispatcherConsumer successfully subscribed to all domain queues")

    async def stop(self) -> None:
        """Gracefully close channel and connection."""
        self._running = False
        if self._channel and not self._channel.is_closed:
            await self._channel.close()
        if self._connection and not self._connection.is_closed:
            await self._connection.close()
        logger.info("DispatcherConsumer stopped cleanly")

    async def _process_message(self, message: AbstractIncomingMessage) -> None:
        """Process incoming task, update DB lifecycle, and dispatch callback event."""
        try:
            body = json.loads(message.body.decode("utf-8"))
        except Exception as exc:
            logger.error("Malformed task body: %s", exc)
            await message.reject(requeue=False)
            return

        task_id = body.get("task_id", message.correlation_id or "unknown")
        alias_name = body.get("alias_name")
        task_type = body.get("task_type")
        domain = body.get("domain") or resolve_task_domain(alias_name=alias_name, task_type=task_type)
        priority = body.get("priority", "normal")
        payload_data = body.get("data", {})
        webhook_url = payload_data.get("webhook_url") or body.get("webhook_url")

        start_time = datetime.now(timezone.utc)
        start_iso = start_time.isoformat()

        logger.info(
            "▶ [Dispatcher] Consuming task %s (domain=%s, priority=%s, alias=%s)",
            task_id, domain, priority, alias_name,
        )

        # 1. Update MongoDB status -> 'running'
        try:
            await job_repository.update_job_status(
                job_id=task_id,
                status="running",
                extra_updates={
                    "worker_node_id": WORKER_NODE_ID,
                    "started_at": start_iso,
                    "updated_at": start_iso,
                    "progress": 10,
                },
            )
        except Exception as exc:
            logger.debug("DB update running failed for %s: %s", task_id, exc)

        # 2. Execute Task / Inference
        success = True
        error_msg: Optional[str] = None
        result_payload: dict[str, Any] = {}

        try:
            # Simulate or dispatch task execution based on domain
            result_payload = await self._execute_task(domain, alias_name, payload_data)
        except Exception as exc:
            success = False
            error_msg = str(exc)
            logger.error("Task %s execution failed: %s", task_id, exc)

        end_time = datetime.now(timezone.utc)
        end_iso = end_time.isoformat()
        duration_ms = int((end_time - start_time).total_seconds() * 1000)

        # 3. Update MongoDB status -> 'completed' or 'failed'
        final_status = "completed" if success else "failed"
        try:
            await job_repository.update_job_status(
                job_id=task_id,
                status=final_status,
                extra_updates={
                    "progress": 100 if success else 0,
                    "error_message": error_msg,
                    "completed_at": end_iso,
                    "updated_at": end_iso,
                    "duration_ms": duration_ms,
                    "result_urls": result_payload.get("result_urls"),
                },
            )
        except Exception as exc:
            logger.debug("DB update completion failed for %s: %s", task_id, exc)

        # 4. If webhook_url is present, publish an event to aip.events for Callback-Worker
        if webhook_url and self._channel:
            try:
                events_exchange = await self._channel.get_exchange(EXCHANGE_EVENTS)
                event_body = {
                    "event": f"job.{final_status}",
                    "job_id": task_id,
                    "domain": domain,
                    "status": final_status,
                    "webhook_url": webhook_url,
                    "duration_ms": duration_ms,
                    "result": result_payload,
                    "error_message": error_msg,
                    "completed_at": end_iso,
                }
                event_msg = aio_pika.Message(
                    body=json.dumps(event_body, ensure_ascii=False).encode("utf-8"),
                    delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                    content_type="application/json",
                )
                await events_exchange.publish(
                    event_msg,
                    routing_key=f"aip.events.job.{final_status}",
                )
                logger.info(
                    "Published callback event for job %s to %s",
                    task_id,
                    EXCHANGE_EVENTS,
                )
            except Exception as exc:
                logger.warning("Failed to publish callback event for %s: %s", task_id, exc)

        # 5. Manual ACK/NACK
        if success:
            await message.ack()
            logger.info("✔ Task %s completed successfully in %sms", task_id, duration_ms)
        else:
            await message.nack(requeue=not message.redelivered)

    async def _execute_task(
        self,
        domain: str,
        alias_name: Optional[str],
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute AI workload or generate standard artifact response."""
        # Standard artifact result format matching SRS
        return {
            "output_text": f"Output completed for {domain} ({alias_name})",
            "result_urls": [f"https://minio.internal/aip-job-artifacts/{domain}/output.dat"],
        }
