import asyncio
import sys
sys.path.insert(0, '/home/namle/AI-Projects/llm-apps/ai_platform/packages')
sys.path.insert(0, '/home/namle/AI-Projects/llm-apps/ai_platform/services/gateway')
from common.database.mongodb import mongo_manager

async def inspect_all_collections():
    await mongo_manager.connect()
    db = mongo_manager.get_database()
    colls = await db.list_collection_names()
    print("ALL COLLECTIONS IN MONGODB ATLAS:", colls)
    for c in colls:
        count = await db[c].count_documents({})
        sample = await db[c].find_one({})
        print(f"\n--- Collection: {c} (Total {count} docs) ---")
        print("Sample doc:", sample)

if __name__ == "__main__":
    asyncio.run(inspect_all_collections())
