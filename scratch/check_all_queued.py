import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

async def check_queued():
    uri = "mongodb+srv://namle:1234@namle.52nsi1k.mongodb.net/ai_platform?appName=namle"
    client = AsyncIOMotorClient(uri)
    db = client["ai_platform"]
    cursor = db["rag_documents"].find({"status": "QUEUED"})
    async for d in cursor:
        print(f"Doc: {d.get('doc_id')}, Title: {d.get('title')}, S3: {d.get('s3_object_name')}, Tenant: {d.get('tenant_id')}")

if __name__ == "__main__":
    asyncio.run(check_queued())

