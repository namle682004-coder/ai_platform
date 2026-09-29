import logging
from datetime import datetime, timezone
from typing import Dict, Any
from common.database.mongodb import mongo_manager

logger = logging.getLogger("aip-jobs.key-maintenance")


class KeyMaintenanceService:
    """
    Monitors API Key lifecycle: expires past-due keys and audits key quota usages.
    """

    async def audit_and_expire_keys(self) -> Dict[str, Any]:
        now_iso = datetime.now(timezone.utc).isoformat()
        expired_count = 0
        try:
            db = mongo_manager.get_database()
            if db is not None:
                res = await db.api_keys.update_many(
                    {
                        "status": "active",
                        "expires_at": {"$exists": True, "$ne": None, "$lt": now_iso},
                    },
                    {"$set": {"status": "expired", "updated_at": now_iso}},
                )
                expired_count = res.modified_count
                if expired_count > 0:
                    logger.info(f"Marked {expired_count} API keys as expired.")
        except Exception as exc:
            logger.warning(f"KeyMaintenanceService error: {exc}")

        return {"expired_keys_count": expired_count}


key_maintenance = KeyMaintenanceService()
