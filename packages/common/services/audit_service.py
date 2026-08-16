import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from common.database.mongodb import mongo_manager

logger = logging.getLogger("aip-audit")


class AuditService:
    """
    Enterprise Activity Audit Log Service recording admin & staff actions to MongoDB Atlas (SRS 10.1).
    """

    def __init__(self):
        self._memory_logs: List[Dict[str, Any]] = [
            {
                "log_id": "log_01DEFAULT",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "actor": "admin@company.com",
                "action": "SYSTEM_STARTUP",
                "resource": "Gateway Microservice",
                "details": "MongoDB Atlas ai_platform database connected.",
                "ip_address": "127.0.0.1"
            }
        ]

    async def log_event(
        self,
        actor: str,
        action: str,
        resource: str,
        details: str,
        ip_address: Optional[str] = "127.0.0.1"
    ) -> Dict[str, Any]:
        record = {
            "log_id": f"log_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')[:18]}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "actor": actor,
            "action": action,
            "resource": resource,
            "details": details,
            "ip_address": ip_address,
        }

        db = mongo_manager.get_database()
        if db is not None:
            try:
                await db.audit_logs.insert_one(dict(record))
            except Exception as e:
                logger.warning(f"MongoDB audit log write error: {e}")

        record.pop("_id", None)
        self._memory_logs.insert(0, record)
        return record

    async def get_logs(self, limit: int = 100) -> List[Dict[str, Any]]:
        db = mongo_manager.get_database()
        if db is not None:
            try:
                cursor = db.audit_logs.find({}, {"_id": 0}).sort("timestamp", -1)
                logs = await cursor.to_list(length=limit)
                if logs:
                    return logs
            except Exception as e:
                logger.warning(f"MongoDB audit log fetch error: {e}")
        return self._memory_logs[:limit]


audit_service = AuditService()
