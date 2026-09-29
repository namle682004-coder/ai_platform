"""
AIP Dedicated Task Dispatcher Worker Main Entrypoint.
Runs TaskConsumer and StaleJobReconciler with graceful shutdown handling.
Compliant with DCP architectural principles and SRS Section 2.3 & 6.1.
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys

from common.database.mongodb import mongo_manager

from .consumer.task_consumer import TaskConsumer
from .reconciler.stale_reconciler import StaleJobReconciler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
)
logger = logging.getLogger("aip-dispatcher.main")

RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")
PREFETCH_COUNT = int(os.getenv("AIP_DISPATCHER_PREFETCH", "5"))


async def main():
    logger.info("Initializing AIP Task Dispatcher Worker...")

    # Initialize MongoDB connection
    await mongo_manager.connect()

    # Initialize components
    consumer = TaskConsumer(rabbitmq_url=RABBITMQ_URL, prefetch_count=PREFETCH_COUNT)
    reconciler = StaleJobReconciler(stale_timeout_seconds=900, scan_interval_seconds=60)

    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    def _shutdown_signal_handler():
        logger.info("Shutdown signal received. Stopping worker...")
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _shutdown_signal_handler)
        except NotImplementedError:
            # Windows fallback
            pass

    # Start tasks
    await consumer.start()
    reconciler_task = asyncio.create_task(reconciler.run_loop())

    logger.info("AIP Dispatcher Worker is running and ready to process AI workloads.")
    await stop_event.wait()

    # Shutdown sequence
    logger.info("Executing graceful shutdown...")
    reconciler.stop()
    reconciler_task.cancel()
    await consumer.stop()
    await mongo_manager.close()
    logger.info("AIP Dispatcher Worker terminated cleanly.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        sys.exit(0)
