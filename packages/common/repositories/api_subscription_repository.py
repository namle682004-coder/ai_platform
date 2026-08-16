from typing import Optional, Dict, Any
from common.database.mongodb import mongo_manager

class MongoApiSubscriptionRepository:
    """MongoDB Atlas implementation for User API Subscriptions."""

    def __init__(self):
        # In-memory cache fallback
        self._subscriptions_cache: Dict[str, Dict[str, Any]] = {}

    async def get_user_subscriptions(self, user_id: str) -> Dict[str, Any]:
        """Fetch user API toggle state from MongoDB or fallback to default."""
        db = mongo_manager.get_database()
        if db is not None:
            try:
                sub = await db.api_subscriptions.find_one({"user_id": user_id}, {"_id": 0})
                if sub and "enabled_apis" in sub:
                    self._subscriptions_cache[user_id] = sub["enabled_apis"]
                    return sub["enabled_apis"]
            except Exception:
                pass
        
        # Fallback to cache or return default
        if user_id in self._subscriptions_cache:
            return self._subscriptions_cache[user_id]
            
        default_state = {
            "Speech to Text": True,
            "Text to Speech": False,
            "LLM Chatbot API": False
        }
        return default_state

    async def update_user_subscriptions(self, user_id: str, enabled_apis: Dict[str, bool]) -> Dict[str, Any]:
        """Upsert the user's API toggle state to MongoDB."""
        self._subscriptions_cache[user_id] = enabled_apis
        db = mongo_manager.get_database()
        if db is not None:
            try:
                await db.api_subscriptions.update_one(
                    {"user_id": user_id},
                    {"$set": {"enabled_apis": enabled_apis}},
                    upsert=True
                )
            except Exception:
                pass
        return enabled_apis

api_subscription_repository = MongoApiSubscriptionRepository()
