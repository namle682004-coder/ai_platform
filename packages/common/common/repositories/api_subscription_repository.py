from typing import Dict, Any
from common.database.mongodb import mongo_manager

class MongoApiSubscriptionRepository:
    """MongoDB Atlas implementation for User API Subscriptions."""

    def _sanitize_api_dict(self, apis: Dict[str, Any]) -> Dict[str, bool]:
        """Keep subscription state for APIs present in the database."""
        return {str(name): bool(enabled) for name, enabled in apis.items()}

    async def get_user_subscriptions(self, user_id: str) -> Dict[str, Any]:
        """Fetch user API toggle state from MongoDB."""
        db = mongo_manager.get_database()
        if db is None:
            raise RuntimeError("MongoDB is unavailable; API subscription state cannot be loaded")

        sub = await db.api_subscriptions.find_one({"user_id": user_id}, {"_id": 0})
        return self._sanitize_api_dict((sub or {}).get("enabled_apis", {}))

    async def update_user_subscriptions(self, user_id: str, enabled_apis: Dict[str, bool]) -> Dict[str, Any]:
        """Directly update / upsert the user's API toggle state to MongoDB."""
        current_state = await self.get_user_subscriptions(user_id)
        current_state.update(self._sanitize_api_dict(enabled_apis))
        db = mongo_manager.get_database()
        if db is None:
            raise RuntimeError("MongoDB is unavailable; API subscription state was not saved")

        await db.api_subscriptions.update_one(
            {"user_id": user_id},
            {"$set": {"enabled_apis": current_state}},
            upsert=True
        )
        return current_state

    async def toggle_api_subscription(self, user_id: str, api_name: str, enabled: bool) -> Dict[str, Any]:
        return await self.update_user_subscriptions(user_id, {api_name: enabled})

    async def get_user_paid_balance(self, user_id: str) -> int:
        """Fetch paid balance credits for user from MongoDB Atlas."""
        db = mongo_manager.get_database()
        if db is None:
            raise RuntimeError("MongoDB is unavailable; paid balance cannot be loaded")
        sub = await db.api_subscriptions.find_one(
            {"user_id": user_id}, {"_id": 0, "paid_balance": 1}
        )
        return int(sub.get("paid_balance", 0)) if sub else 0

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
