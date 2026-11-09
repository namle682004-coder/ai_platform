import requests

# 1. Get embedding
emb_res = requests.post("http://172.16.20.2:8012/v1/embeddings", json={"input": "tỉnh cao bằng kết hợp làm dự án có những mục tiêu nào"})
emb = emb_res.json()["data"][0]["embedding"]

# 2. Search Qdrant
q_res = requests.post("http://172.16.20.2:6333/collections/aip_knowledge_base/points/search", json={
    "vector": emb,
    "limit": 5,
    "with_payload": True
})
hits = q_res.json().get("result", [])
print(f"Total hits: {len(hits)}")
for h in hits:
    p = h.get("payload", {})
    print(f"Vector Score: {h.get('score')}, doc_id: {p.get('doc_id')}, title: {p.get('title')}")
    print(f"Text snippet:\n{p.get('text', '')[:300]}")
    print("-" * 50)

