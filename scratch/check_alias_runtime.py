import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

async def check():
    uri = "mongodb+srv://namle:1234@namle.52nsi1k.mongodb.net/ai_platform?appName=namle"
    client = AsyncIOMotorClient(uri)
    doc = await client["ai_platform"]["aliases"].find_one({"alias_name": "rerank-standard"})
    if not doc:
        doc = await client["ai_platform"]["aliases"].find_one({"name": "rerank-standard"})
    print("Alias rerank-standard:", doc)

if __name__ == "__main__":
    asyncio.run(check())

