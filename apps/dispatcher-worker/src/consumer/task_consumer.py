"""
AIP Production Task Consumer for Dispatcher Worker.
Integrates RabbitMQ domain queues, TaskResolver, gRPC inference client,
jittered exponential backoff, and event publishing to aip.events.
Compliant with DCP architectural principles and SRS Section 2.3 & 6.1.
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
from common.messaging.topology import CORE_TASK_DOMAINS, PRIORITIES, task_queue_name

from ..grpc_client.inference_client import (
    InferenceTerminalError,
    inference_grpc_client,
)
from ..publisher.callback_publisher import callback_publisher
from ..resolver.task_resolver import task_resolver
from ..retry.delayed_retry import RetryPublisher, MAX_RETRIES

logger = logging.getLogger("aip-dispatcher.task-consumer")

WORKER_NODE_ID = os.getenv("AIP_NODE_ID", f"dispatcher-{socket.gethostname()}")



def queue_name(domain: str) -> str:
    return f"q.aip.tasks.{domain}"


class TaskConsumer:
    """Enterprise-grade async consumer for AIP task execution."""

    def __init__(
        self,
        rabbitmq_url: str,
        prefetch_count: int = 1,
    ):
        self.rabbitmq_url = rabbitmq_url
        self.prefetch_count = prefetch_count
        self._retry_publisher = RetryPublisher(rabbitmq_url)
        self._connection: Optional[AbstractRobustConnection] = None
        self._channel: Optional[AbstractChannel] = None
        self._running: bool = False

    async def start(self) -> None:
        """Connect to RabbitMQ and start consuming from all domain queues."""
        self._connection = await aio_pika.connect_robust(self.rabbitmq_url)
        self._channel = await self._connection.channel()
        await self._channel.set_qos(prefetch_count=self.prefetch_count)
        await self._retry_publisher.connect()

        self._running = True
        logger.info(
            "TaskConsumer started on node %s (prefetch=%s). Subscribing to domain queues...",
            WORKER_NODE_ID, self.prefetch_count
        )

        # Subscribe in physical priority order: high -> normal -> batch (DCP Pattern)
        for priority in PRIORITIES:
            for domain in CORE_TASK_DOMAINS:
                q_name = task_queue_name(domain, priority)
                try:
                    queue = await self._channel.get_queue(q_name)
                    await queue.consume(self._process_message)
                    logger.debug("TaskConsumer subscribed: %s (priority=%s)", q_name, priority)
                except Exception as exc:
                    logger.warning("Could not subscribe to queue %s: %s", q_name, exc)

        logger.info("TaskConsumer successfully attached to all domain queues")

    async def stop(self) -> None:
        """Gracefully close channel and connection."""
        self._running = False
        await inference_grpc_client.close()
        await self._retry_publisher.close()
        if self._channel and not self._channel.is_closed:
            await self._channel.close()
        if self._connection and not self._connection.is_closed:
            await self._connection.close()
        logger.info("TaskConsumer cleanly stopped")

    async def _process_message(self, message: AbstractIncomingMessage) -> None:
        """Full pipeline: Message -> Parse -> Run -> gRPC -> Callback -> Ack."""
        try:
            body = json.loads(message.body.decode("utf-8"))
        except Exception as exc:
            logger.error("Malformed task body received: %s. Rejecting.", exc)
            await message.reject(requeue=False)
            return

        task_id = body.get("task_id", message.correlation_id or "unknown")
        alias_name = body.get("alias_name", "chat-general-standard")
        domain = body.get("domain", "chat")
        priority = body.get("priority", "normal")
        payload_data = body.get("data")
        webhook_url = body.get("webhook_url")

        # Thin Task Envelope (DCP Pattern): Load full state from MongoDB if data was not embedded
        if not payload_data:
            try:
                job_doc = await job_repository.get_job(task_id)
                if job_doc:
                    payload_data = job_doc.get("payload") or {}
                    alias_name = job_doc.get("alias_name", alias_name)
                    webhook_url = webhook_url or job_doc.get("webhook_url")
                else:
                    payload_data = {}
            except Exception as exc:
                logger.warning("Failed to fetch full job document for %s from DB: %s", task_id, exc)
                payload_data = {}
        else:
            webhook_url = payload_data.get("webhook_url") or webhook_url

        start_time = datetime.now(timezone.utc)
        start_iso = start_time.isoformat()

        logger.info(
            "▶ [TaskConsumer] Received task %s (domain=%s, alias=%s, priority=%s)",
            task_id, domain, alias_name, priority
        )

        # 1. Update MongoDB job status -> running
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
            logger.debug("DB running update failed for %s: %s", task_id, exc)

        # 2. Resolve target gRPC endpoint
        target = task_resolver.resolve(domain=domain, alias_name=alias_name)
        logger.debug(
            "[TaskConsumer] Resolved %s to gRPC endpoint %s (RPC: %s)",
            task_id, target.grpc_target, target.rpc_method
        )

        # 3. Execute inference via gRPC client directly (Broker handles retries asynchronously)
        success = True
        error_msg: Optional[str] = None
        result_payload: dict[str, Any] = {}

        try:
            result_payload = await inference_grpc_client.execute_inference(
                target_endpoint=target.grpc_target,
                rpc_method=target.rpc_method,
                domain=domain,
                alias_name=alias_name,
                data=payload_data,
                timeout=target.timeout_seconds,
            )
        except InferenceTerminalError as exc:
            success = False
            error_msg = f"Terminal Error: {exc}"
            logger.error("✖ Task %s encountered terminal error: %s (skipping retries)", task_id, exc)
        except Exception as exc:
            success = False
            error_msg = str(exc)
            logger.warning("Task %s inference call failed: %s", task_id, exc)

            retry_count = int(body.get("retry_count", 0))
            if retry_count < MAX_RETRIES:
                # DCP Pattern: Publish to RabbitMQ delayed exchange and ACK immediately!
                try:
                    await self._retry_publisher.publish_retry(
                        task_id=task_id,
                        tenant_id=body.get("tenant_id", "default"),
                        domain=domain,
                        priority=priority,
                        retry_count=retry_count,
                        failure_code="INFERENCE_FAILED",
                        failure_message=error_msg,
                        alias_name=alias_name,
                    )
                    await job_repository.update_job_status(
                        job_id=task_id,
                        status="queued",
                        extra_updates={"error_message": f"Retry {retry_count + 1}/{MAX_RETRIES}: {error_msg}"},
                    )
                    await message.ack()
                    logger.info("✔ Task %s handed over to RabbitMQ delayed retry exchange (0ms blocking)", task_id)
                    return
                except Exception as retry_err:
                    logger.error("Failed to publish delayed retry for %s: %s", task_id, retry_err)

        end_time = datetime.now(timezone.utc)
        end_iso = end_time.isoformat()
        duration_ms = int((end_time - start_time).total_seconds() * 1000)
        final_status = "completed" if success else "failed"

        # 4. Update MongoDB job status -> completed / failed
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
                    "output_text": result_payload.get("output_text") or result_payload.get("translated_text") or result_payload.get("content"),
                },
            )
        except Exception as exc:
            logger.debug("DB completion update failed for %s: %s", task_id, exc)

        # 5. Publish event to aip.events for Callback-Worker
        if webhook_url and self._channel:
            await callback_publisher.publish_event(
                channel=self._channel,
                job_id=task_id,
                domain=domain,
                status=final_status,
                webhook_url=webhook_url,
                duration_ms=duration_ms,
                result=result_payload,
                error_message=error_msg,
                completed_at=end_iso,
            )

        # 6. Final ACK or NACK
        if success:
            await message.ack()
            logger.info("✔ Task %s finished successfully in %sms", task_id, duration_ms)
        else:
            # Exhausted retries -> Dead-letter to DLQ directly
            await message.reject(requeue=False)
            logger.warning("✖ Task %s exhausted retries. Rejected to DLQ.", task_id)
