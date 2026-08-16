import asyncio
from common.database.mongodb import mongo_manager

async def drop():
    # Make sure we connect first if needed
    db = mongo_manager.get_database()
    if db is not None:
        await db.endpoints.drop()
        print("Dropped endpoints collection successfully")
    else:
        print("Failed to get DB instance")

if __name__ == "__main__":
    asyncio.run(drop())
