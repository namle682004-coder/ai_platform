import json
import logging
from typing import Dict, Any, Optional
import aio_pika

logger = logging.getLogger("aip-job-queue")


class DurableJobPublisher:
    """
    Durable RabbitMQ Quorum Queue Publisher.
    Publishes async jobs to topic exchange 'aip.jobs' as specified in SRS Section 7.4.
    """

    def __init__(self, rabbitmq_url: str = "amqp://guest:guest@localhost:5672/"):
        self.rabbitmq_url = rabbitmq_url
        self.connection: Optional[aio_pika.RobustConnection] = None
        self.channel: Optional[aio_pika.RobustChannel] = None
        self.exchange: Optional[aio_pika.RobustExchange] = None

    async def connect(self):
        if not self.connection or self.connection.is_closed:
            try:
                self.connection = await aio_pika.connect_robust(self.rabbitmq_url)
                self.channel = await self.connection.channel()
                # Declare main durable topic exchange 'aip.jobs'
                self.exchange = await self.channel.declare_exchange(
                    "aip.jobs",
                    aio_pika.ExchangeType.TOPIC,
                    durable=True,
                )
                logger.info("Connected to RabbitMQ Job Exchange 'aip.jobs'")
            except Exception as e:
                logger.warning(f"RabbitMQ connection fallback (Local Mode): {e}")

    async def publish_job(self, job_type: str, job_id: str, payload: Dict[str, Any]) -> bool:
        """
        Publishes job message with persistent delivery mode into quorum queues.
        """
        await self.connect()
        message_body = json.dumps({
            "job_id": job_id,
            "job_type": job_type,
            "payload": payload,
        }).encode("utf-8")

        if self.exchange:
            try:
                message = aio_pika.Message(
                    message_body,
                    delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                    content_type="application/json",
                )
                routing_key = f"jobs.{job_type}"
                await self.exchange.publish(message, routing_key=routing_key)
                logger.info(f"Job {job_id} published to RabbitMQ exchange with key '{routing_key}'")
                return True
            except Exception as e:
                logger.error(f"Failed to publish job to RabbitMQ: {e}")
                return False
        return False


durable_job_publisher = DurableJobPublisher()
