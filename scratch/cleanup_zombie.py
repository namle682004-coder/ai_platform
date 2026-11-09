import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

async def cleanup():
    uri = "mongodb+srv://namle:1234@namle.52nsi1k.mongodb.net/ai_platform?appName=namle"
    client = AsyncIOMotorClient(uri)
    db = client["ai_platform"]
    res = await db["rag_documents"].delete_one({"doc_id": "doc_2db8d7b271e2"})
    print("Deleted stale doc_2db8d7b271e2:", res.deleted_count)

if __name__ == "__main__":
    asyncio.run(cleanup())

