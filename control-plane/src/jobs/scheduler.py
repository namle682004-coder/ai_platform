import asyncio
import logging
from typing import Optional
from .task_timeout import task_timeout_reconciler
from .purge import job_data_purger
from .media_reconciler import media_reconciler
from .validation_sweeper import validation_sweeper
from .key_maintenance import key_maintenance

logger = logging.getLogger("aip-jobs.scheduler")


class JobScheduler:
    """
    Periodic Background Maintenance Scheduler for AIP Control Plane.
    Executes timeout reconciliation, storage purging, and key lifecycle checks.
    """

    def __init__(self, interval_seconds: int = 60):
        self._interval = interval_seconds
        self._running = False
        self._task: Optional[asyncio.Task] = None

    def start(self):
        if not self._running:
            self._running = True
            self._task = asyncio.create_task(self._run_loop())
            logger.info(f"JobScheduler started with interval {self._interval}s.")

    async def stop(self):
        if self._running:
            self._running = False
            if self._task:
                self._task.cancel()
                try:
                    await self._task
                except asyncio.CancelledError:
                    pass
            logger.info("JobScheduler stopped.")

    async def _run_loop(self):
        while self._running:
            try:
                await asyncio.sleep(self._interval)
                await self.run_maintenance_cycle()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning(f"Error during maintenance cycle: {exc}")

    async def run_maintenance_cycle(self):
        logger.debug("Executing scheduled maintenance cycle...")
        await task_timeout_reconciler.reconcile_timed_out_tasks()
        await media_reconciler.reconcile_media_assets()
        await key_maintenance.audit_and_expire_keys()
        await validation_sweeper.sweep_stale_validations()
        await job_data_purger.purge_expired_records()


job_scheduler = JobScheduler(interval_seconds=60)
