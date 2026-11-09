import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import datetime

async def check():
    uri = "mongodb+srv://namle:1234@namle.52nsi1k.mongodb.net/ai_platform?appName=namle"
    client = AsyncIOMotorClient(uri)
    db = client["ai_platform"]
    doc = await db["rag_documents"].find_one({"doc_id": "doc_2db8d7b271e2"})
    print("Doc doc_2db8d7b271e2:", doc)
    if doc and doc.get("created_at"):
        dt = datetime.datetime.fromtimestamp(doc["created_at"], tz=datetime.timezone.utc)
        print("Created at UTC:", dt)

if __name__ == "__main__":
    asyncio.run(check())

