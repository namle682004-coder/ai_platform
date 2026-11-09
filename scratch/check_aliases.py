import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

async def check_aliases():
    uri = "mongodb+srv://namle:1234@namle.52nsi1k.mongodb.net/ai_platform?appName=namle"
    client = AsyncIOMotorClient(uri)
    db = client["ai_platform"]
    coll = db["aliases"]
    cursor = coll.find({})
    async for a in cursor:
        print(f"Alias: {a.get('alias') or a.get('alias_name') or a.get('name')}, Target: {a.get('target_url') or a.get('endpoint_url') or a}")

if __name__ == "__main__":
    asyncio.run(check_aliases())

