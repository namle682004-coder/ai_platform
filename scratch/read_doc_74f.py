import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

async def check_doc_content():
    uri = "mongodb+srv://namle:1234@namle.52nsi1k.mongodb.net/ai_platform?appName=namle"
    client = AsyncIOMotorClient(uri)
    db = client["ai_platform"]
    doc = await db["rag_documents"].find_one({"doc_id": "doc_74f0b775d371"})
    print("Document doc_74f0b775d371:")
    for k, v in doc.items():
        if k != "chunks":
            print(f"  {k}: {v}")

if __name__ == "__main__":
    asyncio.run(check_doc_content())

