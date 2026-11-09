import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

async def check_api_logs():
    uri = "mongodb+srv://namle:1234@namle.52nsi1k.mongodb.net/ai_platform?appName=namle"
    client = AsyncIOMotorClient(uri)
    db = client["ai_platform"]
    count = await db["api_logs"].count_documents({})
    print("Total api_logs:", count)
    cursor = db["api_logs"].find({}).sort("_id", -1).limit(5)
    async for l in cursor:
        print(l)

if __name__ == "__main__":
    asyncio.run(check_api_logs())

