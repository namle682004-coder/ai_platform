import sys
import asyncio
import json

sys.path.insert(0, "/home/namle/AI-Projects/llm-apps/ai_platform")

from solutions.rag.infrastructure.adapters.qdrant_adapter import QdrantVectorStoreAdapter
from solutions.rag.infrastructure.adapters.embedding_adapter import GrpcEmbeddingAdapter
from solutions.rag.application.components.reranker import cross_encoder_reranker
from solutions.rag.infrastructure.adapters.llm_adapter import HttpLlmAdapter
from solutions.rag.application.components.prompt_builder import prompt_builder
from solutions.rag.application.use_cases.chat_use_case import CandidateWrapper

async def test_query(q: str):
    print("=" * 80)
    print(f"QUERY: {q}")
    embedder = GrpcEmbeddingAdapter()
    qdrant = QdrantVectorStoreAdapter(collection_name="aip_knowledge_base")
    llm = HttpLlmAdapter()
    
    vec = await embedder.get_embedding(q)
    hits = await qdrant.search(query_vector=vec, tenant_id="global", query_text=q, top_k=10, hybrid=True)
    print(f"Hybrid Hits returned: {len(hits)}")
    for i, h in enumerate(hits[:5]):
        p = h.get("payload", {})
        title = p.get("title")
        doc_id = p.get("doc_id")
        chunk_idx = p.get("chunk_index")
        s = h.get("score", 0.0)
        rrf = h.get("rrf_score", 0.0)
        text_preview = p.get("text", "")[:120].replace("\n", " ")
        print(f"  Hit {i+1}: score={s:.4f} rrf={rrf:.4f} title={title} doc={doc_id} chunk={chunk_idx}")
        print(f"         text: {text_preview}")

    reranked = cross_encoder_reranker.rerank(q, hits, top_n=4, min_threshold=0.30)
    print(f"\nReranked candidates (min_threshold=0.30): {len(reranked)}")
    for i, r in enumerate(reranked):
        p = r.get("payload", {})
        doc_id = p.get("doc_id")
        chunk_idx = p.get("chunk_index")
        s = r.get("score", 0.0)
        raw = r.get("raw_rerank_score", 0.0)
        ret = r.get("retrieval_score", 0.0)
        text_preview = p.get("text", "")[:120].replace("\n", " ")
        print(f"  Rank {i+1}: score={s:.4f} raw={raw:.4f} ret={ret:.4f} doc={doc_id} chunk={chunk_idx}")
        print(f"         text: {text_preview}")

    if not reranked or reranked[0].get("score", 0) < 0.30:
        print("\n--> CIRCUIT BREAKER TRIGGERED: Immediate Refusal")
        return

    wrapped = [CandidateWrapper(c) for c in reranked]
    citations, sys_prompt = prompt_builder.build_context_and_citations(wrapped)
    user_prompt = f"Câu hỏi của người dùng: {q}"

    messages = [
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": user_prompt}
    ]

    print("\nCalling LLM...")
    try:
        answer, p_tokens, c_tokens = await llm.generate(
            messages=messages,
            model="chat-general-standard",
            temperature=0.0,
            max_tokens=512,
        )
        print("\n--- LLM RESPONSE ---")
        print(answer)
        print("--------------------")
    except Exception as e:
        print(f"LLM Error: {e}")

async def main():
    test_queries = [
        "nhiệm vụ A2 của tuần 7 là gì vậy ?",
        "Mục tiêu của tuần 1 thử việc là gì?",
        "nhiệm vụ A9 của tuần 1 là gì?",
        "kế hoạch thử việc tuần 12 có những công việc gì?",
        "Bí quyết du hành vũ trụ đến sao Hỏa là gì?",
        "Công thức nấu món phở bò gia truyền Hà Nội cần những nguyên liệu gì?",
        "Thời tiết Tokyo ngày mai như thế nào?"
    ]
    for q in test_queries:
        await test_query(q)

if __name__ == "__main__":
    asyncio.run(main())
