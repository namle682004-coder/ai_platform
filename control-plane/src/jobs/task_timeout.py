import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any
from common.database.mongodb import mongo_manager

logger = logging.getLogger("aip-jobs.timeout")


class TaskTimeoutReconciler:
    """
    Scans for in-flight tasks that have exceeded their designated timeout.
    Auto-fails timed-out jobs and marks failure reason.
    """

    async def reconcile_timed_out_tasks(self, max_timeout_seconds: int = 300) -> Dict[str, Any]:
        threshold = datetime.now(timezone.utc) - timedelta(seconds=max_timeout_seconds)
        threshold_iso = threshold.isoformat()

        timed_out_count = 0
        try:
            db = mongo_manager.get_database()
            if db is not None:
                cursor = db.jobs.find({
                    "status": "processing",
                    "updated_at": {"$lt": threshold_iso},
                })
                async for job in cursor:
                    job_id = job.get("job_id") or str(job.get("_id"))
                    await db.jobs.update_one(
                        {"_id": job["_id"]},
                        {
                            "$set": {
                                "status": "failed",
                                "error": "Task execution timed out by TaskTimeoutReconciler",
                                "updated_at": datetime.now(timezone.utc).isoformat(),
                            }
                        },
                    )
                    timed_out_count += 1
                    logger.warning(f"Auto-failed timed-out job: {job_id}")
        except Exception as exc:
            logger.warning(f"TaskTimeoutReconciler encountered error: {exc}")

        return {"timed_out_reconciled": timed_out_count}


task_timeout_reconciler = TaskTimeoutReconciler()
