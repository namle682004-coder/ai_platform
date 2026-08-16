from datetime import datetime, timezone
from typing import Dict, Any, List
from common.interfaces.api_logs import IAPILogRepository
from common.database.mongodb import mongo_manager


class MongoAPILogRepository(IAPILogRepository):
    """MongoDB Atlas implementation for API Call Execution Logs."""

    def __init__(self):
        self._logs_cache: List[Dict[str, Any]] = []

    async def log_request(self, log_record: Dict[str, Any]) -> Dict[str, Any]:
        if "timestamp" not in log_record:
            log_record["timestamp"] = datetime.now(timezone.utc).isoformat()
        db = mongo_manager.get_database()
        if db is not None:
            try:
                await db.api_logs.insert_one(dict(log_record))
            except Exception:
                pass
        log_record.pop("_id", None)
        self._logs_cache.insert(0, log_record)
        return log_record

    async def list_recent_logs(self, limit: int = 100) -> List[Dict[str, Any]]:
        db = mongo_manager.get_database()
        if db is not None:
            try:
                cursor = db.api_logs.find({}, {"_id": 0}).sort("timestamp", -1)
                logs = await cursor.to_list(length=limit)
                if logs:
                    for log_item in logs:
                        log_item.pop("_id", None)
                    return logs
            except Exception:
                pass
        return self._logs_cache[:limit]


api_log_repository = MongoAPILogRepository()
