"""
Entrypoint for AIP Callback Worker Service.
Runs dedicated webhook consumer with HMAC signing and SSRF security.
"""

import asyncio
import logging
import signal

from src.configs.settings import gateway_settings
from worker.consumer import CallbackConsumer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("aip-callback")


async def main() -> None:
    logger.info("Starting AIP Dedicated Callback Worker...")

    consumer = CallbackConsumer(
        rabbitmq_url=gateway_settings.rabbitmq_url,
        prefetch_count=10,
    )
    await consumer.start()

    stop_event = asyncio.Event()

    def _handle_exit():
        logger.info("Received shutdown signal. Stopping Callback Worker...")
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _handle_exit)
        except NotImplementedError:
            pass

    logger.info("AIP Callback Worker is running. Waiting for events...")
    await stop_event.wait()

    await consumer.stop()
    logger.info("AIP Callback Worker shut down successfully.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
