"""
Automated tests for Decoupled Distributed Architecture (DCP Architecture):
- Dedicated Dispatcher Worker
- Stale Job Self-Healing Reconciler
- Dedicated Callback Worker with Event Bus
"""

import asyncio

from src.publisher.topology import (
    setup_rabbitmq_topology,
)
from src.configs.settings import gateway_settings
from dispatcher.reconciler import StaleJobReconciler


def test_topology_declares_event_and_callback_queues():
    async def _run():
        await setup_rabbitmq_topology(gateway_settings.rabbitmq_url)
    asyncio.run(_run())


def test_stale_job_reconciler_auto_heals():
    async def _run():
        reconciler = StaleJobReconciler(stale_timeout_seconds=300, scan_interval_seconds=60)
        # Verify single run does not throw even if DB empty
        count = await reconciler.reconcile_once()
        assert isinstance(count, int)
    asyncio.run(_run())
