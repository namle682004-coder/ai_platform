"""
AIP Self-Healing Stale Job Reconciler.
Periodically scans MongoDB for jobs stuck in 'running' state past their timeout threshold.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from common.repositories.mongo_repositories import job_repository

logger = logging.getLogger("aip-dispatcher.reconciler")


class StaleJobReconciler:
    """Detects and fails or requeues dead worker jobs."""

    def __init__(
        self,
        stale_timeout_seconds: int = 900,  # 15 minutes default
        scan_interval_seconds: int = 60,
    ):
        self.stale_timeout_seconds = stale_timeout_seconds
        self.scan_interval_seconds = scan_interval_seconds
        self._running = False

    async def reconcile_once(self) -> int:
        """Single reconciliation pass across active MongoDB collections."""
        try:
            db = job_repository.get_db()
            if db is None:
                return 0

            threshold = datetime.now(timezone.utc).timestamp() - self.stale_timeout_seconds
            cursor = db.jobs.find({
                "status": "running",
            })

            reconciled = 0
            async for job in cursor:
                updated_at_str = job.get("updated_at") or job.get("started_at") or job.get("created_at")
                if not updated_at_str:
                    continue

                try:
                    updated_at = datetime.fromisoformat(updated_at_str.replace("Z", "+00:00")).timestamp()
                except Exception:
                    continue

                if updated_at < threshold:
                    job_id = job.get("job_id")
                    logger.warning(
                        "[StaleReconciler] Auto-healing orphaned job %s stuck since %s",
                        job_id, updated_at_str
                    )
                    await job_repository.update_job_status(
                        job_id=job_id,
                        status="failed",
                        extra_updates={
                            "error_message": f"Job timed out: worker node heartbeat expired after {self.stale_timeout_seconds}s",
                            "reconciled_by": "StaleJobReconciler",
                            "completed_at": datetime.now(timezone.utc).isoformat(),
                        },
                    )
                    reconciled += 1

            if reconciled > 0:
                logger.info("[StaleReconciler] Reconciled %d orphaned jobs to failed state", reconciled)
            return reconciled

        except Exception as exc:
            logger.debug("[StaleReconciler] Error during reconciliation pass: %s", exc)
            return 0

    async def run_loop(self) -> None:
        """Continuous background loop for deployment."""
        self._running = True
        logger.info(
            "StaleJobReconciler started (interval=%ds, timeout=%ds)",
            self.scan_interval_seconds, self.stale_timeout_seconds
        )
        while self._running:
            await self.reconcile_once()
            await asyncio.sleep(self.scan_interval_seconds)

    def stop(self) -> None:
        self._running = False
