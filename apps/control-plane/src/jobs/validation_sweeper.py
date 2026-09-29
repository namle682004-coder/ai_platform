import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any
from common.database.mongodb import mongo_manager

logger = logging.getLogger("aip-jobs.sweeper")


class ValidationSweeper:
    """
    Sweeps expired temporary verification tokens, pending onboarding approvals,
    and stale pre-flight validation cache.
    """

    async def sweep_stale_validations(self, ttl_days: int = 14) -> Dict[str, Any]:
        cutoff = datetime.now(timezone.utc) - timedelta(days=ttl_days)
        cutoff_iso = cutoff.isoformat()

        swept_count = 0
        try:
            db = mongo_manager.get_database()
            if db is not None and "verification_tokens" in await db.list_collection_names():
                res = await db.verification_tokens.delete_many({
                    "created_at": {"$lt": cutoff_iso},
                })
                swept_count = res.deleted_count
        except Exception as exc:
            logger.warning(f"ValidationSweeper error: {exc}")

        return {"swept_validations": swept_count}


validation_sweeper = ValidationSweeper()
