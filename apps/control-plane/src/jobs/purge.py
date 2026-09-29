import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any
from common.database.mongodb import mongo_manager

logger = logging.getLogger("aip-jobs.purge")


class JobDataPurger:
    """
    Purges historical finished/failed jobs and temporary storage records
    exceeding retention policy (default 7 days).
    """

    async def purge_expired_records(self, retention_days: int = 7) -> Dict[str, Any]:
        cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
        cutoff_iso = cutoff.isoformat()

        purged_jobs = 0
        purged_logs = 0
        try:
            db = mongo_manager.get_database()
            if db is not None:
                # 1. Delete old completed or failed jobs
                res_jobs = await db.jobs.delete_many({
                    "status": {"$in": ["completed", "failed", "cancelled"]},
                    "created_at": {"$lt": cutoff_iso},
                })
                purged_jobs = res_jobs.deleted_count

                # 2. Delete old api_call_logs
                if "api_call_logs" in await db.list_collection_names():
                    res_logs = await db.api_call_logs.delete_many({
                        "timestamp": {"$lt": cutoff_iso},
                    })
                    purged_logs = res_logs.deleted_count

                logger.info(f"Purged {purged_jobs} expired jobs and {purged_logs} old logs.")
        except Exception as exc:
            logger.warning(f"JobDataPurger encountered error: {exc}")

        return {"purged_jobs": purged_jobs, "purged_logs": purged_logs}


job_data_purger = JobDataPurger()
