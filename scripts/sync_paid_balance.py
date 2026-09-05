import asyncio
import sys

# Add packages and services to sys.path
sys.path.insert(0, '/home/namle/AI-Projects/llm-apps/ai_platform/packages')
sys.path.insert(0, '/home/namle/AI-Projects/llm-apps/ai_platform/services/gateway')

from common.database.mongodb import mongo_manager

async def sync_db_fields():
    await mongo_manager.connect()
    db = mongo_manager.get_database()
    if db is None:
        print("Error: Could not connect to MongoDB Atlas.")
        return

    # Update all documents in api_subscriptions to guarantee paid_balance field exists
    result = await db.api_subscriptions.update_many(
        {"paid_balance": {"$exists": False}},
        {"$set": {"paid_balance": 0}}
    )
    print(f"Updated docs with paid_balance: {result.modified_count}")

    # Fetch user_staff_01 document
    doc = await db.api_subscriptions.find_one({"user_id": "user_staff_01"})
    print("Document for user_staff_01 in MongoDB Atlas:")
    print(doc)

if __name__ == "__main__":
    asyncio.run(sync_db_fields())
