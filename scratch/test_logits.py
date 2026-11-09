import sys
import asyncio
sys.path.insert(0, '/home/namle/AI-Projects/llm-apps/ai_platform')
from solutions.rag.infrastructure.adapters.qdrant_adapter import QdrantVectorStoreAdapter
from solutions.rag.infrastructure.adapters.embedding_adapter import GrpcEmbeddingAdapter
from solutions.rag.application.components.reranker import NeuralCrossEncoderReranker
import numpy as np

async def test():
    qdrant = QdrantVectorStoreAdapter(collection_name='aip_knowledge_base')
    embedder = GrpcEmbeddingAdapter()
    reranker = NeuralCrossEncoderReranker()
    q = 'Công thức nấu món phở bò gia truyền Hà Nội cần những nguyên liệu và gia vị gì?'
    vec = await embedder.get_embedding(q)
    hits = await qdrant.search(query_vector=vec, tenant_id='global', query_text=q, top_k=5, hybrid=True)
    ranker = reranker._get_ranker()
    passages = [{'id': idx, 'text': c.get('payload', {}).get('text', '')} for idx, c in enumerate(hits)]
    
    query_passage_pairs = [[q, passage['text']] for passage in passages]
    input_text = ranker.tokenizer.encode_batch(query_passage_pairs)
    input_ids = np.array([e.ids for e in input_text])
    token_type_ids = np.array([e.type_ids for e in input_text])
    attention_mask = np.array([e.attention_mask for e in input_text])
    onnx_input = {
        'input_ids': input_ids.astype(np.int64),
        'attention_mask': attention_mask.astype(np.int64),
        'token_type_ids': token_type_ids.astype(np.int64)
    }
    outputs = ranker.session.run(None, onnx_input)
    logits = outputs[0]
    print('logits shape:', logits.shape)
    print('logits:\n', logits)
    if logits.shape[1] == 1:
        scores = 1 / (1 + np.exp(-logits.flatten()))
    else:
        exp_logits = np.exp(logits)
        scores = exp_logits[:, 1] / np.sum(exp_logits, axis=1)
    print('calculated scores:\n', scores)

if __name__ == '__main__':
    asyncio.run(test())
