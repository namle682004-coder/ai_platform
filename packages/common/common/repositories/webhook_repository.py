from datetime import datetime, timezone
from typing import Dict, Any, List
from common.interfaces.webhooks import IWebhookRepository
from common.database.mongodb import mongo_manager


class MongoWebhookRepository(IWebhookRepository):
    """MongoDB Atlas implementation for Tenant Webhooks."""

    def __init__(self):
        self._webhooks_cache: Dict[str, Dict[str, Any]] = {}

    async def create_webhook(self, webhook_record: Dict[str, Any]) -> Dict[str, Any]:
        if "created_at" not in webhook_record:
            webhook_record["created_at"] = datetime.now(timezone.utc).isoformat()
        db = mongo_manager.get_database()
        if db is not None:
            try:
                await db.webhooks.insert_one(dict(webhook_record))
            except Exception:
                pass
        webhook_record.pop("_id", None)
        self._webhooks_cache[webhook_record["webhook_id"]] = webhook_record
        return webhook_record

    async def list_webhooks(self, tenant_id: str) -> List[Dict[str, Any]]:
        db = mongo_manager.get_database()
        if db is not None:
            try:
                cursor = db.webhooks.find({"tenant_id": tenant_id}, {"_id": 0})
                hooks = await cursor.to_list(length=100)
                if hooks:
                    for h in hooks:
                        h.pop("_id", None)
                        self._webhooks_cache[h["webhook_id"]] = h
                    return hooks
            except Exception:
                pass
        return [h for h in self._webhooks_cache.values() if h.get("tenant_id") == tenant_id]

    async def delete_webhook(self, webhook_id: str) -> bool:
        if webhook_id in self._webhooks_cache:
            del self._webhooks_cache[webhook_id]
            db = mongo_manager.get_database()
            if db is not None:
                try:
                    await db.webhooks.delete_one({"webhook_id": webhook_id})
                except Exception:
                    pass
            return True
        return False


webhook_repository = MongoWebhookRepository()
