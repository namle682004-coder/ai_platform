from flashrank import Ranker, RerankRequest
import sys
sys.path.insert(0, '/home/namle/AI-Projects/llm-apps/ai_platform')
from solutions.rag.infrastructure.adapters.qdrant_adapter import QdrantVectorStoreAdapter
from solutions.rag.infrastructure.adapters.embedding_adapter import GrpcEmbeddingAdapter
import asyncio

async def test():
    qdrant = QdrantVectorStoreAdapter(collection_name='aip_knowledge_base')
    embedder = GrpcEmbeddingAdapter()
    q = 'Công thức nấu món phở bò gia truyền Hà Nội cần những nguyên liệu và gia vị gì?'
    vec = await embedder.get_embedding(q)
    hits = await qdrant.search(query_vector=vec, tenant_id='global', query_text=q, top_k=5, hybrid=True)
    for idx, h in enumerate(hits):
        t = h.get('payload', {}).get('text', '')
        print(f"--- HIT {idx} (Title: {h.get('payload', {}).get('title')}) ---")
        print(t[:200])

if __name__ == '__main__':
    asyncio.run(test())
