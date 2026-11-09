import sys
import re
sys.path.insert(0, '/home/namle/AI-Projects/llm-apps/ai_platform')
from solutions.rag.infrastructure.adapters.qdrant_adapter import QdrantVectorStoreAdapter
from solutions.rag.infrastructure.adapters.embedding_adapter import GrpcEmbeddingAdapter
from solutions.rag.application.components.reranker import NeuralCrossEncoderReranker
import asyncio

STOPWORDS = {
    "là", "và", "của", "cho", "trong", "được", "các", "những", "một", "với", "này",
    "đó", "khi", "tại", "từ", "ra", "đến", "có", "không", "gì", "nào", "bao", "nhiêu",
    "ai", "sao", "thế", "để", "về", "theo", "như", "thì", "mà", "bị", "do", "bởi"
}

def extract_salient_words(query: str):
    tokens = [w.lower() for w in re.findall(r"[\w]+", query) if len(w) >= 2]
    return [w for w in tokens if w not in STOPWORDS and not w.isdigit()]

async def test_all_20():
    qdrant = QdrantVectorStoreAdapter(collection_name='aip_knowledge_base')
    embedder = GrpcEmbeddingAdapter()
    reranker = NeuralCrossEncoderReranker()
    
    with open('/home/namle/AI-Projects/llm-apps/ai_platform/benchmarks/rag/datasets/enterprise/frozen_test/enterprise_golden_v2.jsonl') as f:
        import json
        cases = [json.loads(line) for line in f]
    
    print(f"Testing {len(cases)} cases with Lexical-Salience Grounded Reranker...")
    for c in cases:
        q = c['question']
        cid = c['case_id']
        is_ood = not c['answerable']
        vec = await embedder.get_embedding(q)
        hits = await qdrant.search(query_vector=vec, tenant_id='global', query_text=q, top_k=5, hybrid=True)
        
        salient = extract_salient_words(q)
        # Apply reranking with lexical grounding check
        candidates = []
        for h in hits:
            cand = h.copy()
            chunk_text = cand.get('payload', {}).get('text', '').lower()
            overlap = sum(1 for w in salient if w in chunk_text) if salient else 1
            cand['_salient_overlap'] = overlap
            candidates.append(cand)
            
        filtered = reranker.rerank(q, candidates, top_n=4, min_threshold=0.75)
        
        # If salient terms exist but Top-1 candidate has 0 overlap: cap score
        if filtered:
            top_cand = filtered[0]
            if salient and top_cand.get('_salient_overlap', 0) == 0:
                filtered = [] # Trigger Circuit Breaker
                
        status = "REFUSED (Circuit Breaker)" if not filtered else f"ACCEPTED (Top={filtered[0]['score']})"
        expected = "SHOULD REFUSE" if is_ood else "SHOULD ACCEPT"
        match = (not filtered and is_ood) or (filtered and not is_ood)
        flag = "OK" if match else "MISMATCH"
        print(f"[{cid}] [{expected}] -> {status} => {flag}")

if __name__ == '__main__':
    asyncio.run(test_all_20())
