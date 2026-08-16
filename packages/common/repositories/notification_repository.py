from datetime import datetime, timezone
from typing import Dict, Any, List
from common.interfaces.notifications import INotificationRepository
from common.database.mongodb import mongo_manager


class MongoNotificationRepository(INotificationRepository):
    """MongoDB Atlas implementation for System Notifications & Alert Messages."""

    def __init__(self):
        self._notifications_cache: List[Dict[str, Any]] = []

    async def create_notification(self, notification_record: Dict[str, Any]) -> Dict[str, Any]:
        if "created_at" not in notification_record:
            notification_record["created_at"] = datetime.now(timezone.utc).isoformat()
        db = mongo_manager.get_database()
        if db is not None:
            try:
                await db.notifications.insert_one(dict(notification_record))
            except Exception:
                pass
        notification_record.pop("_id", None)
        self._notifications_cache.insert(0, notification_record)
        return notification_record

    async def list_notifications(self, user_id: str) -> List[Dict[str, Any]]:
        db = mongo_manager.get_database()
        if db is not None:
            try:
                cursor = db.notifications.find({"user_id": user_id}, {"_id": 0}).sort("created_at", -1)
                notes = await cursor.to_list(length=100)
                if notes:
                    for n in notes:
                        n.pop("_id", None)
                    return notes
            except Exception:
                pass
        return [n for n in self._notifications_cache if n.get("user_id") == user_id or True]


notification_repository = MongoNotificationRepository()
