import asyncio
from common.database.mongodb import mongo_manager
async def check():
    db = mongo_manager.get_database()
    users = await db.users.find().to_list(10)
    for u in users: print(u.get('user_id'), u.get('enabled_apis'))
if __name__ == '__main__':
    asyncio.run(check())
