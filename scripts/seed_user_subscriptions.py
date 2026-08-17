import asyncio
import sys

sys.path.insert(0, '/home/namle/AI-Projects/llm-apps/ai_platform/packages')
sys.path.insert(0, '/home/namle/AI-Projects/llm-apps/ai_platform/services/gateway')

from common.database.mongodb import mongo_manager
from common.repositories.api_subscription_repository import api_subscription_repository

async def seed_subs():
    await mongo_manager.connect()
    db = mongo_manager.get_database()
    if db is None:
        print("Cannot connect to MongoDB")
        return

    # Delete existing subscription for user_staff_01 to force re-evaluation or update
    await db.api_subscriptions.delete_one({"user_id": "user_staff_01"})
    print("Deleted old subscription document.")

    # Get user subscriptions (which will auto-generate the default dict with 13 keys)
    default_subs = await api_subscription_repository.get_user_subscriptions("user_staff_01")
    
    # Save/Upsert it back
    await api_subscription_repository.update_user_subscriptions("user_staff_01", default_subs)
    print("Seeded new 13 APIs subscription dict into MongoDB Atlas for user_staff_01:")
    print(default_subs)

if __name__ == "__main__":
    asyncio.run(seed_subs())
