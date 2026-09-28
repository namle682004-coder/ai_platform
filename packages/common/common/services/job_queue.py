"""
Durable RabbitMQ Quorum Queue Publisher for AIP Platform.
Synchronized with official aip.tasks topic topology.
"""

import json
import logging
import os
from typing import Any, Dict, Optional
import aio_pika

logger = logging.getLogger("aip-job-queue")


class DurableJobPublisher:
    """
    Durable RabbitMQ Publisher for background async jobs.
    Publishes to topic exchange 'aip.tasks' with domain routing.
    """

    def __init__(self, rabbitmq_url: Optional[str] = None):
        self.rabbitmq_url = rabbitmq_url or os.getenv("RABBITMQ_URL", "amqp://aip@localhost:5672/aip")
        self.connection: Optional[aio_pika.RobustConnection] = None
        self.channel: Optional[aio_pika.RobustChannel] = None
        self.exchange: Optional[aio_pika.RobustExchange] = None

    async def connect(self):
        if not self.connection or self.connection.is_closed:
            try:
                self.connection = await aio_pika.connect_robust(self.rabbitmq_url)
                self.channel = await self.connection.channel()
                self.exchange = await self.channel.declare_exchange(
                    "aip.tasks",
                    aio_pika.ExchangeType.TOPIC,
                    durable=True,
                )
                logger.info("Connected to RabbitMQ Task Exchange 'aip.tasks'")
            except Exception as e:
                logger.warning(f"RabbitMQ connection fallback (Local Mode): {e}")

    async def publish_job(
        self,
        job_type: str,
        job_id: str,
        payload: Dict[str, Any],
        priority: str = "normal",
        domain: Optional[str] = None,
    ) -> bool:
        """
        Publishes job message with persistent delivery mode.
        """
        await self.connect()
        clean_domain = domain or job_type
        if clean_domain.startswith("tasks."):
            clean_domain = clean_domain[len("tasks."):]

        message_body = json.dumps({
            "job_id": job_id,
            "task_id": job_id,
            "job_type": job_type,
            "task_type": job_type,
            "domain": clean_domain,
            "priority": priority,
            "payload": payload,
        }).encode("utf-8")

        if self.exchange:
            try:
                message = aio_pika.Message(
                    message_body,
                    delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                    content_type="application/json",
                    correlation_id=job_id,
                )
                routing_key = f"aip.tasks.{clean_domain}.{priority}"
                await self.exchange.publish(message, routing_key=routing_key)
                logger.info(f"Job {job_id} published to RabbitMQ exchange with key '{routing_key}'")
                return True
            except Exception as e:
                logger.error(f"Failed to publish job to RabbitMQ: {e}")
                return False
        return False


durable_job_publisher = DurableJobPublisher()
