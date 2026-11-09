path = "platform/gateway/src/admin/endpoint_catalog.py"
with open(path, "r", encoding="utf-8") as f:
    text = f.read()

rag_endpoint = '''    {
        "endpoint_id": "/v1/rag/chat",
        "api_id": "api_rag",
        "name": "Enterprise RAG Chatbot",
        "category": "Generative AI",
        "status": "active",
        "description": "Enterprise Retrieval-Augmented Generation with Hybrid Vector Search & Cross-Encoder Reranker.",
        "icon": "fa-brain",
        "free_quota": "20,000 tokens",
        "unit": "token",
        "overview": {
            "title": "Enterprise RAG Knowledge Chatbot",
            "summary": "Hệ thống AI Hỏi đáp Tri thức Trực ban Chuẩn Hybrid Retrieval & Reranker phục vụ tra cứu chính xác văn bản nội bộ.",
            "features": [
                "Truy xuất lai (Hybrid Retrieval: Dense Vector + Sparse BM25)",
                "Xếp hạng chéo (Cross-Encoder Reranker BGE-Reranker-v2-m3)",
                "Cổng bảo vệ chống bịa đặt (Anti-Hallucination Gatekeeper)",
                "Trích dẫn nguồn tài liệu và số trang cụ thể"
            ]
        },
        "document": {
            "endpoint_url": "http://172.16.20.2:8000/v1/rag/chat",
            "method": "POST",
            "content_type": "application/json",
            "headers": [
                {"name": "Authorization", "type": "string", "required": True, "desc": "Bearer API Key của bạn"},
                {"name": "Content-Type", "type": "string", "required": True, "desc": "application/json"}
            ],
            "parameters": [
                {"name": "query", "type": "string", "required": True, "desc": "Câu hỏi tra cứu"},
                {"name": "model", "type": "string", "required": False, "desc": "Mô hình ngôn ngữ (mặc định chat-general-standard)"}
            ],
            "sample_response": '{\\n  "answer": "Nội dung trả lời chính xác có trích dẫn...",\\n  "citations": [{"index": 1, "title": "Báo cáo", "page_number": 1}],\\n  "model": "chat-general-standard"\\n}'
        },
        "pricing": {
            "free_quota": "20,000 tokens miễn phí mỗi tháng",
            "pay_as_you_go": "15 VNĐ / 1,000 tokens",
            "billing_cycle": "Thanh toán dựa trên tổng Input + Output Tokens"
        }
    },
'''

text_norm = text.replace("\r\n", "\n")
target = "NEW_ENDPOINTS = [\n"
if target in text_norm and "/v1/rag/chat" not in text_norm:
    text_norm = text_norm.replace(target, target + rag_endpoint)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text_norm)
    print("Added /v1/rag/chat to endpoint_catalog.py successfully!")
else:
    print("Endpoint already present or target not found.")

