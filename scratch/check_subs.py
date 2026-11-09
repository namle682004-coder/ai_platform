import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

async def check():
    uri = "mongodb+srv://namle:1234@namle.52nsi1k.mongodb.net/ai_platform?appName=namle"
    client = AsyncIOMotorClient(uri)
    db = client["ai_platform"]
    cursor = db["api_subscriptions"].find({})
    async for s in cursor:
        print("Subscription:", s)

if __name__ == "__main__":
    asyncio.run(check())

