import asyncio
from qdrant_client import AsyncQdrantClient
import httpx

async def check():
    # Embedding
    async with httpx.AsyncClient() as client:
        res = await client.post("http://172.16.20.2:8012/v1/embeddings", json={"input": "tỉnh cao bằng kết hợp làm dự án có những mục tiêu nào"})
        emb = res.json()["data"][0]["embedding"]
        
        q_client = AsyncQdrantClient(url="http://172.16.20.2:6333")
        hits = await q_client.search(
            collection_name="aip_knowledge_base",
            query_vector=emb,
            limit=5
        )
        print(f"Total hits: {len(hits)}")
        for h in hits:
            print(f"Score: {h.score}, doc_id: {h.payload.get('doc_id')}, title: {h.payload.get('title')}")
            print(f"Text snippet: {h.payload.get('text', '')[:200]}")
            print("-" * 40)

if __name__ == "__main__":
    asyncio.run(check())

