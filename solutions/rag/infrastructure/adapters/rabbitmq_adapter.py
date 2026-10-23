"""
Production-Grade Asynchronous RabbitMQ Broker Adapter for AIP RAG Solution.
Compliant with DDD Clean Architecture MessageBrokerPort.
Provides persistent pooled connections, robust self-healing reconnection,
health checks, and exponential-backoff retry for zero message loss.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from typing import Any, Dict, Optional

import aio_pika
from aio_pika.abc import AbstractChannel, AbstractRobustConnection
from aio_pika.pool import Pool

from ...config import rag_settings
from ...domain.ports import MessageBrokerPort

logger = logging.getLogger("aip-rag.adapter.rabbitmq")


class RabbitMQBrokerAdapter(MessageBrokerPort):
    """
    Enterprise asynchronous RabbitMQ message publisher using aio-pika connection & channel pooling.
    Eliminates blocking I/O, prevents connection churn, and self-heals after network blips.
    """

    def __init__(
        self,
        rabbitmq_url: Optional[str] = None,
        max_connection_pool_size: int = 2,
        max_channel_pool_size: int = 10,
        connection_timeout: float = 10.0,
    ) -> None:
        self.rabbitmq_url = rabbitmq_url or rag_settings.rabbitmq_url
        self.max_connection_pool_size = max_connection_pool_size
        self.max_channel_pool_size = max_channel_pool_size
        self.connection_timeout = connection_timeout

        self._connection_pool: Optional[Pool[AbstractRobustConnection]] = None
        self._channel_pool: Optional[Pool[AbstractChannel]] = None
        self._lock = asyncio.Lock()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._is_closing = False

    def _ensure_active_loop(self) -> None:
        """Reset pools if the running event loop has changed or closed."""
        try:
            current_loop = asyncio.get_running_loop()
            if self._loop is None or self._loop != current_loop or self._loop.is_closed():
                self._connection_pool = None
                self._channel_pool = None
                self._loop = current_loop
        except RuntimeError:
            pass

    async def _get_connection(self) -> AbstractRobustConnection:
        """Establish a self-healing robust connection."""
        return await aio_pika.connect_robust(
            self.rabbitmq_url,
            timeout=self.connection_timeout,
        )

    async def _get_channel(self) -> AbstractChannel:
        """Acquire a channel from an active pooled connection."""
        pool = await self._get_connection_pool()
        async with pool.acquire() as connection:
            return await connection.channel()

    async def _get_connection_pool(self) -> Pool[AbstractRobustConnection]:
        self._ensure_active_loop()
        if self._connection_pool is None:
            async with self._lock:
                if self._connection_pool is None:
                    self._connection_pool = Pool(
                        self._get_connection,
                        max_size=self.max_connection_pool_size,
                    )
        return self._connection_pool

    async def _get_channel_pool(self) -> Pool[AbstractChannel]:
        self._ensure_active_loop()
        if self._channel_pool is None:
            async with self._lock:
                if self._channel_pool is None:
                    self._channel_pool = Pool(
                        self._get_channel,
                        max_size=self.max_channel_pool_size,
                    )
        return self._channel_pool

    async def publish(
        self,
        queue_name: str,
        payload: Dict[str, Any],
        max_retries: int = 3,
    ) -> bool:
        """
        Publish a persistent message to the target queue with automatic reconnection & retry.
        Guarantees that network blips do not silently drop ingestion tasks.
        """
        if self._is_closing:
            logger.warning("RabbitMQ adapter is closing; cannot publish to queue '%s'", queue_name)
            return False

        message_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        last_error: Optional[Exception] = None

        for attempt in range(1, max_retries + 1):
            try:
                channel_pool = await self._get_channel_pool()
                async with channel_pool.acquire() as channel:
                    # Declare queue as durable to guarantee surviving broker restarts
                    await channel.declare_queue(queue_name, durable=True)
                    
                    message = aio_pika.Message(
                        body=message_bytes,
                        delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                        content_type="application/json",
                        timestamp=time.time(),
                    )
                    await channel.default_exchange.publish(
                        message,
                        routing_key=queue_name,
                    )
                    logger.info("Successfully published task to RabbitMQ queue '%s' (attempt %d)", queue_name, attempt)
                    return True

            except Exception as exc:
                last_error = exc
                logger.warning(
                    "RabbitMQ publish attempt %d/%d to queue '%s' failed: %s",
                    attempt,
                    max_retries,
                    queue_name,
                    exc,
                )
                # Invalidate channel pool if a fatal connection/channel error occurs
                if attempt < max_retries:
                    backoff = 0.2 * (2 ** (attempt - 1))
                    await asyncio.sleep(backoff)
                    async with self._lock:
                        # Reset pools to re-trigger connect_robust on next attempt
                        if self._channel_pool is not None:
                            try:
                                await self._channel_pool.close()
                            except Exception:
                                pass
                            self._channel_pool = None

        logger.error(
            "Failed to publish to RabbitMQ queue '%s' after %d attempts. Last error: %s",
            queue_name,
            max_retries,
            last_error,
        )
        return False

    async def is_healthy(self) -> bool:
        """Check live connectivity to RabbitMQ broker."""
        try:
            channel_pool = await self._get_channel_pool()
            async with channel_pool.acquire() as channel:
                return not channel.is_closed
        except Exception:
            return False

    async def close(self) -> None:
        """Gracefully release all connections and channels in the pool."""
        self._is_closing = True
        async with self._lock:
            if self._channel_pool is not None:
                try:
                    await self._channel_pool.close()
                except Exception:
                    pass
                self._channel_pool = None

            if self._connection_pool is not None:
                try:
                    await self._connection_pool.close()
                except Exception:
                    pass
                self._connection_pool = None
        logger.info("Closed RabbitMQ connection and channel pools.")


# Global singleton instance
rabbitmq_broker = RabbitMQBrokerAdapter()
