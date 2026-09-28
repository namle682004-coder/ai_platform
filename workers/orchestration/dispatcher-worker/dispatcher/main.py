"""
Entrypoint for AIP Dispatcher Worker Service.
Runs the multi-domain task consumer and the self-healing stale job reconciler.
"""

import asyncio
import logging
import signal
import sys

from common.database.mongodb import mongo_manager
from src.configs.settings import gateway_settings
from dispatcher.consumer import DispatcherConsumer
from dispatcher.reconciler import StaleJobReconciler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("aip-dispatcher")


async def main() -> None:
    logger.info("Starting AIP Dispatcher Worker Service...")

    # 1. Connect MongoDB
    try:
        await mongo_manager.connect(uri=gateway_settings.mongo_uri, db_name="ai_platform")
        logger.info("Connected to MongoDB: %s", gateway_settings.mongo_uri)
    except Exception as exc:
        logger.error("Failed to connect to MongoDB: %s", exc)
        sys.exit(1)

    # 2. Start Dispatcher Consumer
    consumer = DispatcherConsumer(gateway_settings.rabbitmq_url, prefetch_count=10)
    await consumer.start()

    # 3. Start Stale Job Reconciler
    reconciler = StaleJobReconciler(stale_timeout_seconds=600, scan_interval_seconds=60)
    await reconciler.start()

    stop_event = asyncio.Event()

    def _handle_exit():
        logger.info("Received shutdown signal. Stopping services...")
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _handle_exit)
        except NotImplementedError:
            # Windows compatibility
            pass

    logger.info("AIP Dispatcher Worker is running. Waiting for tasks...")
    await stop_event.wait()

    # Shutdown
    await reconciler.stop()
    await consumer.stop()
    logger.info("AIP Dispatcher Worker shut down successfully.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
