import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

async def check_docs():
    uri = "mongodb+srv://namle:1234@namle.52nsi1k.mongodb.net/ai_platform?appName=namle"
    client = AsyncIOMotorClient(uri)
    db = client["ai_platform"]
    coll = db["rag_documents"]
    
    cursor = coll.find({})
    async for d in cursor:
        print(f"ID: {d.get('doc_id')}, Tenant: {d.get('tenant_id')}, Filename: {d.get('filename')}, Title: {d.get('title')}, Status: {d.get('status')}, Chunks: {d.get('total_chunks')}")

if __name__ == "__main__":
    asyncio.run(check_docs())

