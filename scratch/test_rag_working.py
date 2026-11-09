import requests
import json

questions = [
    "Dự án tỉnh Cao Bằng đánh giá cán bộ bằng gì?",
    "Nghị định 335 có mấy bước và gồm những bước nào?",
    "Các vấn đề phát sinh trong quá trình đánh giá cán bộ là gì?"
]

for q in questions:
    payload = {
        "query": q,
        "model": "chat-general-standard",
        "stream": False
    }
    headers = {
        "Authorization": "Bearer aip_live_valid_test_key_12345",
        "Content-Type": "application/json"
    }

    res = requests.post("http://172.16.20.2:8000/v1/rag/chat", json=payload, headers=headers)
    data = res.json()
    print(f"\nQ: {q}")
    print(f"Status: {res.status_code}")
    print(f"Answer: {data.get('answer')}")
    print(f"Citations: {len(data.get('citations', []))}")

