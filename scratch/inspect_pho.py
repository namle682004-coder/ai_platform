import sys
import asyncio
sys.path.insert(0, '/home/namle/AI-Projects/llm-apps/ai_platform')
from solutions.rag.infrastructure.adapters.qdrant_adapter import QdrantVectorStoreAdapter
from solutions.rag.infrastructure.adapters.embedding_adapter import GrpcEmbeddingAdapter
from solutions.rag.application.components.reranker import NeuralCrossEncoderReranker

async def inspect():
    qdrant = QdrantVectorStoreAdapter(collection_name='aip_knowledge_base')
    embedder = GrpcEmbeddingAdapter()
    reranker = NeuralCrossEncoderReranker()
    
    q = "Công thức nấu món phở bò gia truyền Hà Nội cần những nguyên liệu và gia vị gì?"
    vec = await embedder.get_embedding(q)
    hits = await qdrant.search(query_vector=vec, tenant_id='global', query_text=q, top_k=5, hybrid=True)
    print("Qdrant hits count:", len(hits))
    for h in hits:
        print("Hit text:", h.get("payload", {}).get("text", "")[:80])
    
    # Now let's see what FlashRank produces on these hits
    filtered = reranker.rerank(q, hits, top_n=4, min_threshold=0.75)
    print("Filtered count:", len(filtered))
    for f in filtered:
        print("Filtered score:", f.get("score"), "Text:", f.get("text", "")[:80])

if __name__ == '__main__':
    asyncio.run(inspect())
