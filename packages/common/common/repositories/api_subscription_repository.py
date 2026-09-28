from typing import Dict, Any
from common.database.mongodb import mongo_manager

CANONICAL_APIS = [
    "LLM Chatbot API",
    "Speech to Text API",
    "Text to Speech API",
    "CCCD / ID Card OCR API",
    "Content Moderation API",
    "Text Embeddings API",
    "Translation API",
]

def normalize_api_name(name: str) -> str:
    if not name:
        return ""
    n = name.strip()
    low = n.lower()
    if "speech to text" in low:
        return "Speech to Text API"
    if "text to speech" in low:
        return "Text to Speech API"
    if "llm" in low or "chatbot" in low:
        return "LLM Chatbot API"
    if "id" in low or "cccd" in low or "ocr" in low:
        return "CCCD / ID Card OCR API"
    if "moderation" in low:
        return "Content Moderation API"
    if "embedding" in low:
        return "Text Embeddings API"
    if "translat" in low:
        return "Translation API"
    return n

class MongoApiSubscriptionRepository:
    """MongoDB Atlas implementation for User API Subscriptions."""

    def __init__(self):
        self._subscriptions_cache: Dict[str, Dict[str, Any]] = {}

    def _sanitize_api_dict(self, apis: Dict[str, Any]) -> Dict[str, bool]:
        """Normalize dictionary down to strictly the 7 canonical API keys."""
        cleaned: Dict[str, bool] = {k: True for k in CANONICAL_APIS}
        if not apis:
            return cleaned

        for k, v in apis.items():
            norm = normalize_api_name(k)
            if norm in cleaned:
                cleaned[norm] = bool(v)

        return cleaned

    async def get_user_subscriptions(self, user_id: str) -> Dict[str, Any]:
        """Fetch user API toggle state from MongoDB or fallback to default."""
        db = mongo_manager.get_database()
        if db is not None:
            try:
                sub = await db.api_subscriptions.find_one({"user_id": user_id}, {"_id": 0})
                if sub and "enabled_apis" in sub:
                    sanitized = self._sanitize_api_dict(sub["enabled_apis"])
                    self._subscriptions_cache[user_id] = sanitized
                    return sanitized
            except Exception:
                pass

        if user_id in self._subscriptions_cache:
            return self._subscriptions_cache[user_id]

        default_state = {k: True for k in CANONICAL_APIS}
        return default_state

    async def update_user_subscriptions(self, user_id: str, enabled_apis: Dict[str, bool]) -> Dict[str, Any]:
        """Directly update / upsert the user's API toggle state to MongoDB."""
        current_state = await self.get_user_subscriptions(user_id)

        for k, v in enabled_apis.items():
            norm = normalize_api_name(k)
            if norm in current_state:
                current_state[norm] = bool(v)

        self._subscriptions_cache[user_id] = current_state
        db = mongo_manager.get_database()
        if db is not None:
            try:
                await db.api_subscriptions.update_one(
                    {"user_id": user_id},
                    {"$set": {"enabled_apis": current_state}},
                    upsert=True
                )
            except Exception:
                pass
        return current_state

    async def toggle_api_subscription(self, user_id: str, api_name: str, enabled: bool) -> Dict[str, Any]:
        norm = normalize_api_name(api_name)
        return await self.update_user_subscriptions(user_id, {norm: enabled})

    async def get_user_paid_balance(self, user_id: str) -> int:
        """Fetch paid balance credits for user from MongoDB Atlas."""
        db = mongo_manager.get_database()
        if db is not None:
            try:
                sub = await db.api_subscriptions.find_one({"user_id": user_id}, {"_id": 0, "paid_balance": 1})
                if sub and "paid_balance" in sub:
                    return int(sub["paid_balance"])
            except Exception:
                pass
        return 500000

    async def recharge_user_balance(
        self,
        user_id: str,
        add_credits: int,
        amount: int = 0,
        package: str = "Standard",
        project: str = "default",
    ) -> int:
        """Recharge balance credits and insert payment transaction into MongoDB Atlas."""
        from datetime import datetime, timezone
        import uuid
        db = mongo_manager.get_database()
        current_bal = await self.get_user_paid_balance(user_id)
        new_bal = current_bal + int(add_credits)

        if db is not None:
            try:
                await db.api_subscriptions.update_one(
                    {"user_id": user_id},
                    {"$set": {"paid_balance": new_bal}},
                    upsert=True,
                )
                payment_record = {
                    "payment_id": f"pay_{uuid.uuid4().hex[:12]}",
                    "user_id": user_id,
                    "credits_added": add_credits,
                    "amount_vnd": amount,
                    "package_name": package,
                    "project": project,
                    "status": "completed",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                await db.payments.insert_one(payment_record)
            except Exception:
                pass

        return new_bal

api_subscription_repository = MongoApiSubscriptionRepository()

