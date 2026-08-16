import asyncio
from common.database.mongodb import mongo_manager
async def check():
    db = mongo_manager.get_database()
    if db is not None:
        count = await db.users.count_documents({})
        print('Users count in DB:', count)
    else:
        print("DB is None")
if __name__ == '__main__':
    asyncio.run(check())
