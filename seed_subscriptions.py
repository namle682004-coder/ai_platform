import asyncio
from common.database.mongodb import mongo_manager

async def seed_api_subscriptions():
    db = mongo_manager.get_database()
    if db is not None:
        # Default state to insert
        default_state = {
            "Speech to Text": True,
            "Text to Speech": False,
            "LLM Chatbot API": False
        }
        
        users_to_seed = ["user_staff_01", "user_b9361c5fdf", "user_409d822ba1"]
        
        for uid in users_to_seed:
            await db.api_subscriptions.update_one(
                {"user_id": uid},
                {"$setOnInsert": {"user_id": uid, "enabled_apis": default_state}},
                upsert=True
            )
            print(f"Inserted/Ensured api_subscriptions for {uid}")
            
        print("Database collection 'api_subscriptions' has been created and seeded!")
    else:
        print("Failed to connect to MongoDB.")

if __name__ == '__main__':
    asyncio.run(seed_api_subscriptions())
