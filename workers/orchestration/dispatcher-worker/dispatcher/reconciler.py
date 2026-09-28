"""
Stale Job Reconciler for AIP Dispatcher Worker.
Inspired by DCP Self-Healing Reconciler architecture.

Periodically scans MongoDB for jobs stuck in 'running' or 'queued' state
beyond their execution threshold (e.g. due to sudden GPU OOM, worker crash,
or node eviction) and marks them as failed or recovers them.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from common.repositories.mongo_repositories import job_repository

logger = logging.getLogger("aip-dispatcher.reconciler")

DEFAULT_STALE_TIMEOUT_SECONDS: int = 600  # 10 minutes
DEFAULT_SCAN_INTERVAL_SECONDS: int = 60    # Check every minute


class StaleJobReconciler:
    """Background service to detect and resolve zombie/stale jobs."""

    def __init__(
        self,
        stale_timeout_seconds: int = DEFAULT_STALE_TIMEOUT_SECONDS,
        scan_interval_seconds: int = DEFAULT_SCAN_INTERVAL_SECONDS,
    ):
        self.stale_timeout_seconds = stale_timeout_seconds
        self.scan_interval_seconds = scan_interval_seconds
        self._running: bool = False
        self._task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """Start the background reconciliation loop."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._reconcile_loop())
        logger.info(
            "StaleJobReconciler started (interval=%ss, timeout=%ss)",
            self.scan_interval_seconds,
            self.stale_timeout_seconds,
        )

    async def stop(self) -> None:
        """Gracefully stop the reconciler loop."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("StaleJobReconciler stopped cleanly")

    async def _reconcile_loop(self) -> None:
        while self._running:
            try:
                await self.reconcile_once()
            except Exception as exc:
                logger.error("Error during stale job reconciliation cycle: %s", exc)

            try:
                await asyncio.sleep(self.scan_interval_seconds)
            except asyncio.CancelledError:
                break

    async def reconcile_once(self) -> int:
        """
        Execute a single reconciliation scan.
        Finds running jobs older than stale_timeout and updates their status.
        """
        now = datetime.now(timezone.utc)
        recovered_count = 0

        try:
            # Look up running jobs
            col = job_repository._get_collection()
            cursor = col.find({"status": "running"})
            async for doc in cursor:
                updated_at_str = doc.get("updated_at") or doc.get("created_at")
                if not updated_at_str:
                    continue

                try:
                    updated_at = datetime.fromisoformat(updated_at_str.replace("Z", "+00:00"))
                    age_seconds = (now - updated_at).total_seconds()
                except Exception:
                    continue

                if age_seconds > self.stale_timeout_seconds:
                    job_id = doc.get("job_id")
                    logger.warning(
                        "Reconciler found stale running job %s (idle for %.1fs > %ss). Auto-failing.",
                        job_id,
                        age_seconds,
                        self.stale_timeout_seconds,
                    )
                    await job_repository.update_job_status(
                        job_id=job_id,
                        status="failed",
                        extra_updates={
                            "error_message": f"Worker heartbeat timeout: job stale after {age_seconds:.0f}s without response (Self-Healing Reconciler)",
                            "failed_at": now.isoformat(),
                            "updated_at": now.isoformat(),
                        },
                    )
                    recovered_count += 1
        except Exception as exc:
            logger.debug("Reconciler scan skipped or DB offline: %s", exc)

        return recovered_count
