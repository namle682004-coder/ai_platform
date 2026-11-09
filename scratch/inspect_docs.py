import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

async def inspect():
    uri = "mongodb+srv://namle:1234@namle.52nsi1k.mongodb.net/ai_platform?appName=namle"
    client = AsyncIOMotorClient(uri)
    db = client["ai_platform"]
    colls = await db.list_collection_names()
    print("Collections in ai_platform:", colls)
    
    for c_name in colls:
        if any(k in c_name.lower() for k in ["doc", "rag", "know", "file"]):
            coll = db[c_name]
            count = await coll.count_documents({})
            print(f"\nCollection {c_name} (total {count}):")
            cursor = coll.find({}).sort("_id", -1).limit(10)
            async for doc in cursor:
                doc_summary = {k: v for k, v in doc.items() if k not in ["content", "raw_content", "chunks", "embedding"]}
                if "chunks" in doc:
                    doc_summary["chunks_len"] = len(doc["chunks"]) if isinstance(doc["chunks"], list) else doc["chunks"]
                print(" -", doc_summary)

if __name__ == "__main__":
    asyncio.run(inspect())

