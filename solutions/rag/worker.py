"""
Production Worker Entrypoint for AIP RAG Solution.
Starts asynchronous RabbitMQ ingestion consumer.
"""

from __future__ import annotations

import asyncio
import logging

from solutions.rag.interfaces.worker.consumer import RagWorkerConsumer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


async def main() -> None:
    consumer = RagWorkerConsumer()
    await consumer.run()


if __name__ == "__main__":
    asyncio.run(main())
