from typing import Optional, Dict, Any
from common.database.mongodb import mongo_manager

CANONICAL_APIS = [
    "Speech to Text API",
    "Text to Speech API",
    "LLM Chatbot API",
    "Image Generation API",
    "Content Moderation API"
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
    if "image" in low:
        return "Image Generation API"
    if "moderation" in low:
        return "Content Moderation API"
    return n if n.endswith(" API") else f"{n} API"

class MongoApiSubscriptionRepository:
    """MongoDB Atlas implementation for User API Subscriptions."""

    def __init__(self):
        # In-memory cache fallback with clean canonical keys
        self._subscriptions_cache: Dict[str, Dict[str, Any]] = {}

    def _sanitize_api_dict(self, apis: Dict[str, Any]) -> Dict[str, bool]:
        """Normalize any legacy dictionary down to strictly the 5 canonical API keys."""
        cleaned: Dict[str, bool] = {
            "Speech to Text API": False,
            "Text to Speech API": False,
            "LLM Chatbot API": False,
            "Image Generation API": False,
            "Content Moderation API": False
        }
        if not apis:
            cleaned["Speech to Text API"] = True
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
        
        # Fallback to cache or return default
        if user_id in self._subscriptions_cache:
            return self._subscriptions_cache[user_id]
            
        default_state = {
            "Speech to Text API": True,
            "Text to Speech API": False,
            "LLM Chatbot API": False,
            "Image Generation API": False,
            "Content Moderation API": False
        }
        return default_state

    async def update_user_subscriptions(self, user_id: str, enabled_apis: Dict[str, bool]) -> Dict[str, Any]:
        """Directly update / upsert the user's API toggle state to MongoDB without duplicate keys."""
        # Get existing state first to ensure we merge cleanly
        current_state = await self.get_user_subscriptions(user_id)
        
        # Merge only updated fields
        for k, v in enabled_apis.items():
            norm = normalize_api_name(k)
            if norm in current_state:
                current_state[norm] = bool(v)

        self._subscriptions_cache[user_id] = current_state
        db = mongo_manager.get_database()
        if db is not None:
            try:
                # Replace enabled_apis with strictly the 5 clean canonical keys (eliminates duplicates in DB)
                await db.api_subscriptions.update_one(
                    {"user_id": user_id},
                    {"$set": {"enabled_apis": current_state}},
                    upsert=True
                )
            except Exception:
                pass
        return current_state

    async def get_user_paid_balance(self, user_id: str) -> int:
        """Fetch user paid credit balance from MongoDB or cache."""
        db = mongo_manager.get_database()
        if db is not None:
            try:
                sub = await db.api_subscriptions.find_one({"user_id": user_id}, {"_id": 0, "paid_balance": 1})
                if sub and "paid_balance" in sub:
                    return int(sub["paid_balance"])
            except Exception:
                pass
        return 0

    async def recharge_user_balance(self, user_id: str, add_credits: int, amount: str, package: str, project: str = "default") -> int:
        """Atomically increase paid balance in MongoDB Atlas and record transaction."""
        db = mongo_manager.get_database()
        current_bal = await self.get_user_paid_balance(user_id)
        new_bal = current_bal + add_credits

        if db is not None:
            try:
                # Update subscription balance
                await db.api_subscriptions.update_one(
                    {"user_id": user_id},
                    {"$inc": {"paid_balance": add_credits}},
                    upsert=True
                )

                # Record permanent payment record
                from datetime import datetime, timezone
                import secrets
                payment_doc = {
                    "user_id": user_id,
                    "txn_ref": f"VNP{secrets.randbelow(89999999) + 10000000}",
                    "date": datetime.now(timezone.utc).strftime("%Y/%m/%d %H:%M"),
                    "status": "SUCCESS",
                    "amount": amount,
                    "package": package,
                    "project": project,
                    "credits_added": add_credits,
                    "txn_no": str(secrets.randbelow(89999999) + 10000000),
                }
                await db.payments.insert_one(payment_doc)
            except Exception:
                pass

        return new_bal

api_subscription_repository = MongoApiSubscriptionRepository()
