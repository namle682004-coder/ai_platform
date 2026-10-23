import asyncio
import sys

sys.path.extend([
    "/home/namle/AI-Projects/llm-apps/ai_platform",
    "/home/namle/AI-Projects/llm-apps/ai_platform/platform/gateway",
    "/home/namle/AI-Projects/llm-apps/ai_platform/solutions/rag",
    "/home/namle/AI-Projects/llm-apps/ai_platform/packages/common",
    "/home/namle/AI-Projects/llm-apps/ai_platform/packages/contracts",
])
from solutions.rag.infrastructure.adapters.qdrant_adapter import QdrantVectorStoreAdapter
from solutions.rag.infrastructure.adapters.embedding_adapter import GrpcEmbeddingAdapter

async def main():
    store = QdrantVectorStoreAdapter(base_url="http://localhost:6333", collection_name="aip_knowledge_base")
    embedder = GrpcEmbeddingAdapter(http_url="http://localhost:8001/v1")
    q = "Mục tiêu vị trí việc làm của Hiệu trưởng là gì?"
    vec = await embedder.get_embedding(q)

    dense = await store.search_dense(query_vector=vec, tenant_id="proj_default", top_k=40)
    print("=== DENSE RESULTS ===")
    found_dense = False
    for rank, d in enumerate(dense, 1):
        p = d.get("payload", {})
        doc = p.get("doc_id")
        c_idx = p.get("chunk_index")
        if doc == "doc_vtvl_hiệu_trưởng_cb" and c_idx == 3:
            print(f">>> FOUND TARGET CHUNK 3: Dense Rank={rank}, Score={d.get('score')}")
            found_dense = True
        elif rank <= 4:
            print(f"Dense Rank {rank}: {doc} chunk {c_idx}, score={d.get('score')}")
    if not found_dense:
        print(">>> TARGET CHUNK 3 NOT IN TOP 40 DENSE")

    sparse = await store.search_sparse_keywords(query_text=q, tenant_id="proj_default", top_k=40)
    print("=== SPARSE RESULTS ===")
    found_sparse = False
    for rank, s in enumerate(sparse, 1):
        p = s.get("payload", {})
        doc = p.get("doc_id")
        c_idx = p.get("chunk_index")
        if doc == "doc_vtvl_hiệu_trưởng_cb" and c_idx == 3:
            print(f">>> FOUND TARGET CHUNK 3: Sparse Rank={rank}, BM25={s.get('score')}")
            found_sparse = True
        elif rank <= 4:
            print(f"Sparse Rank {rank}: {doc} chunk {c_idx}, score={s.get('score')}")
    if not found_sparse:
        print(">>> TARGET CHUNK 3 NOT IN TOP 40 SPARSE")

    hybrid = await store.search(query_vector=vec, query_text=q, tenant_id="proj_default", top_k=15)
    print("=== HYBRID FUSION RESULTS ===")
    for rank, h in enumerate(hybrid, 1):
        p = h.get("payload", {})
        print(f"Hybrid {rank}: Doc={p.get('doc_id')}, Chunk={p.get('chunk_index')}, RRF={h.get('rrf_score')}, BM25={h.get('bm25_score')}")

if __name__ == "__main__":
    asyncio.run(main())
