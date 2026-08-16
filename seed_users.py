import asyncio
from common.database.mongodb import mongo_manager
from common.repositories.user_repository import DEFAULT_USERS

async def seed_users():
    db = mongo_manager.get_database()
    if db is not None:
        for user in DEFAULT_USERS:
            await db.users.update_one(
                {"user_id": user["user_id"]},
                {"$setOnInsert": user},
                upsert=True
            )
        print("Seeded DEFAULT_USERS successfully.")

if __name__ == '__main__':
    asyncio.run(seed_users())
