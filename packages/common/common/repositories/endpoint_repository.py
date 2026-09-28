from typing import Optional, Dict, Any
from common.interfaces.endpoints import IEndpointRepository
from common.database.mongodb import mongo_manager

DEFAULT_ENDPOINTS = [
    {
        "endpoint_id": "/v1/chat/completions",
        "path": "/v1/chat/completions",
        "method": "POST",
        "api_id": "api_llm",
        "name": "LLM Chatbot API",
        "category": "Generative AI",
        "status": "active",
        "description": "Standard OpenAI-compatible Chat completion interface powered by Qwen2.5-1.5B-Instruct.",
        "icon": "fa-robot",
        "free_quota": "50,000 tokens",
        "unit": "token",
        "overview": {
            "title": "Qwen2.5-1.5B Generative AI Engine",
            "summary": "Mô hình ngôn ngữ lớn tối ưu cho tiếng Việt và tiếng Anh, hỗ trợ suy luận logic, giải đáp hội thoại và trích xuất dữ liệu có cấu trúc.",
            "features": [
                "Tương thích 100% chuẩn OpenAI Chat Completions API",
                "Hỗ trợ streaming Server-Sent Events (SSE)",
                "Độ trễ thấp, tối ưu hóa cho phần cứng cục bộ",
                "Hỗ trợ đa ngôn ngữ Anh - Việt chuyên sâu"
            ]
        },
        "document": {
            "endpoint_url": "http://localhost:8000/v1/chat/completions",
            "method": "POST",
            "content_type": "application/json",
            "headers": [
                {"name": "Authorization", "type": "string", "required": True, "desc": "Bearer <YOUR_API_KEY>"},
                {"name": "Content-Type", "type": "string", "required": True, "desc": "application/json"}
            ],
            "parameters": [
                {"name": "model", "type": "string", "required": True, "desc": "chat-general-standard"},
                {"name": "messages", "type": "array", "required": True, "desc": "Danh sách tin nhắn hội thoại [role, content]"},
                {"name": "stream", "type": "boolean", "required": False, "desc": "Bật chế độ SSE stream từng token (mặc định: false)"}
            ],
            "sample_response": '{\n  "id": "chatcmpl-01HXGWEXAMPLE",\n  "object": "chat.completion",\n  "choices": [{\n    "index": 0,\n    "message": {\n      "role": "assistant",\n      "content": "Xin chào! Tôi là trợ lý AI trên nền tảng AIP."\n    },\n    "finish_reason": "stop"\n  }],\n  "usage": { "prompt_tokens": 12, "completion_tokens": 15, "total_tokens": 27 }\n}'
        },
        "pricing": {
            "free_quota": "50,000 tokens miễn phí mỗi tháng",
            "pay_as_you_go": "10 VNĐ / 1,000 tokens",
            "billing_cycle": "Thanh toán dựa trên tổng Input + Output Tokens"
        }
    },
    {
        "endpoint_id": "/v1/audio/transcriptions",
        "path": "/v1/audio/transcriptions",
        "method": "POST",
        "api_id": "api_stt",
        "name": "Speech to Text API",
        "category": "Speech Recognition",
        "status": "active",
        "description": "Speech-to-Text inference endpoint powered by Faster-Whisper.",
        "icon": "fa-microphone",
        "free_quota": "10,000 blocks",
        "unit": "block",
        "overview": {
            "title": "Faster-Whisper Speech-to-Text Engine",
            "summary": "Dịch vụ chuyển đổi giọng nói thành văn bản tiếng Việt và đa ngôn ngữ với độ chính xác cao.",
            "features": [
                "Tương thích chuẩn OpenAI /v1/audio/transcriptions",
                "Hỗ trợ đa định dạng âm thanh: WAV, MP3, OGG, M4A",
                "Tự động nhận diện ngôn ngữ và căn chỉnh dấu tiếng Việt",
                "Tốc độ xử lý siêu nhanh dựa trên engine CTranslate2"
            ]
        },
        "document": {
            "endpoint_url": "http://localhost:8000/v1/audio/transcriptions",
            "method": "POST",
            "content_type": "multipart/form-data",
            "headers": [
                {"name": "Authorization", "type": "string", "required": True, "desc": "Bearer <YOUR_API_KEY>"}
            ],
            "parameters": [
                {"name": "file", "type": "file", "required": True, "desc": "Tệp âm thanh (WAV, MP3, FLAC)"},
                {"name": "model", "type": "string", "required": False, "desc": "stt-vn-standard"},
                {"name": "language", "type": "string", "required": False, "desc": "Mã ngôn ngữ (ví dụ: vi, en)"}
            ],
            "sample_response": '{\n  "text": "Xin chào! Đây là hệ thống nhận dạng giọng nói AIP STT.",\n  "language": "vi",\n  "duration": 3.42\n}'
        },
        "pricing": {
            "free_quota": "10,000 blocks miễn phí mỗi tháng",
            "pay_as_you_go": "150 VNĐ / block (1 block = 15 giây âm thanh)",
            "billing_cycle": "Thanh toán theo thời lượng audio thực tế"
        }
    },
    {
        "endpoint_id": "/v1/audio/speech",
        "path": "/v1/audio/speech",
        "method": "POST",
        "api_id": "api_tts",
        "name": "Text to Speech API",
        "category": "Speech Synthesis",
        "status": "active",
        "description": "Standard OpenAI-compatible Text-to-Speech synthesis with natural Vietnamese neural voices.",
        "icon": "fa-volume-high",
        "free_quota": "100,000 characters",
        "unit": "character",
        "overview": {
            "title": "Neural Speech Synthesis Engine",
            "summary": "Tổng hợp giọng nói tiếng Việt tự nhiên đa vùng miền (Bắc, Nam) với ngữ điệu biểu cảm cao.",
            "features": [
                "Tương thích 100% chuẩn OpenAI /v1/audio/speech",
                "Hỗ trợ 4 giọng đọc chuẩn: banmai (nữ Bắc), leminh (nam Bắc), lannhi (nữ Nam), namminh (nam Nam)",
                "Xuất định dạng âm thanh phổ biến: MP3, WAV",
                "Phản hồi độ trễ thấp, âm thanh trong trẻo"
            ]
        },
        "document": {
            "endpoint_url": "http://localhost:8000/v1/audio/speech",
            "method": "POST",
            "content_type": "application/json",
            "headers": [
                {"name": "Authorization", "type": "string", "required": True, "desc": "Bearer <YOUR_API_KEY>"},
                {"name": "Content-Type", "type": "string", "required": True, "desc": "application/json"}
            ],
            "parameters": [
                {"name": "model", "type": "string", "required": True, "desc": "tts-vi-standard"},
                {"name": "input", "type": "string", "required": True, "desc": "Nội dung văn bản cần chuyển thành giọng nói"},
                {"name": "voice", "type": "string", "required": False, "desc": "banmai, leminh, lannhi, namminh (mặc định: banmai)"},
                {"name": "response_format", "type": "string", "required": False, "desc": "mp3 hoặc wav (mặc định: mp3)"}
            ],
            "sample_response": "[Binary Audio Stream (audio/mpeg hoặc audio/wav)]"
        },
        "pricing": {
            "free_quota": "100,000 ký tự miễn phí mỗi tháng",
            "pay_as_you_go": "20 VNĐ / 1,000 ký tự",
            "billing_cycle": "Thanh toán theo số lượng ký tự văn bản chuyển đổi"
        }
    },
    {
        "endpoint_id": "/v1/ocr/id-card",
        "path": "/v1/ocr/id-card",
        "method": "POST",
        "api_id": "api_ocr_id",
        "name": "CCCD / ID Card OCR API",
        "category": "OCR & Reader",
        "status": "active",
        "description": "Vietnamese Citizen Identity Card (CCCD 12 số) OCR & QR code auto-extraction.",
        "icon": "fa-id-card",
        "free_quota": "500 images",
        "unit": "image",
        "overview": {
            "title": "Vietnamese National ID Card (CCCD) OCR Engine",
            "summary": "Trích xuất thông tin tự động từ Căn cước công dân gắn chip hoặc mã vạch bằng kết hợp OCR thị giác máy tính và quét mã QR.",
            "features": [
                "Trích xuất chính xác 100%: Số CCCD, Họ tên, Ngày sinh, Giới tính, Quê quán, Thường trú, Hạn dùng",
                "Tích hợp giải mã QR Code 2D tốc độ cao",
                "Chống sai lệch thông tin bằng thuật toán so khớp chéo QR và OCR",
                "Chuẩn hóa dữ liệu trả về định dạng JSON có phân giải độ tin cậy"
            ]
        },
        "document": {
            "endpoint_url": "http://localhost:8000/v1/ocr/id-card",
            "method": "POST",
            "content_type": "multipart/form-data",
            "headers": [
                {"name": "Authorization", "type": "string", "required": True, "desc": "Bearer <YOUR_API_KEY>"}
            ],
            "parameters": [
                {"name": "image", "type": "file", "required": True, "desc": "Ảnh chụp mặt trước hoặc mặt sau CCCD (JPG, PNG)"}
            ],
            "sample_response": '{\n  "status": "success",\n  "data": {\n    "id_number": "038204021019",\n    "full_name": "LÊ THẾ NAM",\n    "dob": "06/08/2004",\n    "gender": "Nam",\n    "place_of_origin": "Thanh Sơn, Thị xã Nghi Sơn, Thanh Hóa",\n    "place_of_residence": "Thôn Phúc Lý, Thanh Sơn, Thị xã Nghi Sơn, Thanh Hóa",\n    "expires": "06/08/2029"\n  }\n}'
        },
        "pricing": {
            "free_quota": "500 ảnh miễn phí",
            "pay_as_you_go": "250 VNĐ / ảnh",
            "billing_cycle": "Thanh toán dựa trên số lượt nhận dạng ảnh"
        }
    },
    {
        "endpoint_id": "/v1/moderations",
        "path": "/v1/moderations",
        "method": "POST",
        "api_id": "api_moderation",
        "name": "Content Moderation API",
        "category": "Trust & Safety",
        "status": "active",
        "description": "Standard OpenAI-compatible Content Moderation for hate speech, harassment, self-harm, sexual, and violence.",
        "icon": "fa-shield-halved",
        "free_quota": "10,000 requests",
        "unit": "request",
        "overview": {
            "title": "AI Safety & Content Moderation Engine",
            "summary": "Kiểm duyệt nội dung độc hại tự động hỗ trợ cả tiếng Việt và tiếng Anh, giúp bảo vệ nền tảng người dùng.",
            "features": [
                "Tương thích 100% chuẩn OpenAI /v1/moderations",
                "Phân loại 5 danh mục an toàn: hate, harassment, self-harm, sexual, violence",
                "Cung cấp cờ cảnh báo (flagged) và điểm số rủi ro (category_scores)",
                "Kết hợp bộ luật ngữ nghĩa tiếng Việt sâu cùng mô hình phân loại nơ-ron"
            ]
        },
        "document": {
            "endpoint_url": "http://localhost:8000/v1/moderations",
            "method": "POST",
            "content_type": "application/json",
            "headers": [
                {"name": "Authorization", "type": "string", "required": True, "desc": "Bearer <YOUR_API_KEY>"},
                {"name": "Content-Type", "type": "string", "required": True, "desc": "application/json"}
            ],
            "parameters": [
                {"name": "input", "type": "string", "required": True, "desc": "Văn bản cần kiểm duyệt nội dung"},
                {"name": "model", "type": "string", "required": False, "desc": "moderation-multimodal (mặc định)"}
            ],
            "sample_response": '{\n  "id": "modr-01HXGWEXAMPLE",\n  "model": "moderation-multimodal",\n  "results": [{\n    "flagged": true,\n    "categories": { "hate": false, "harassment": true, "self_harm": false, "sexual": false, "violence": true },\n    "category_scores": { "hate": 0.05, "harassment": 0.92, "self_harm": 0.01, "sexual": 0.02, "violence": 0.96 }\n  }]\n}'
        },
        "pricing": {
            "free_quota": "10,000 requests miễn phí mỗi tháng",
            "pay_as_you_go": "5 VNĐ / request",
            "billing_cycle": "Thanh toán dựa trên số lượt kiểm duyệt"
        }
    },
    {
        "endpoint_id": "/v1/embeddings",
        "path": "/v1/embeddings",
        "method": "POST",
        "api_id": "api_embeddings",
        "name": "Text Embeddings API",
        "category": "Natural Language Processing",
        "status": "active",
        "description": "Standard OpenAI-compatible Vector Embeddings API for semantic search & RAG.",
        "icon": "fa-brain",
        "free_quota": "100,000 tokens",
        "unit": "token",
        "overview": {
            "title": "Neural Vector Embeddings Engine",
            "summary": "Biến đổi văn bản thành vector đặc trưng nhiều chiều phục vụ tìm kiếm ngữ nghĩa, phân loại và hệ thống RAG.",
            "features": [
                "Tương thích 100% chuẩn OpenAI /v1/embeddings",
                "Hỗ trợ trích xuất vector dạng số thực 384 hoặc 768 chiều",
                "Xử lý song song nhiều câu (batch input) tốc độ cao",
                "Tối ưu cho bài toán Semantic Search và RAG Knowledge Base"
            ]
        },
        "document": {
            "endpoint_url": "http://localhost:8000/v1/embeddings",
            "method": "POST",
            "content_type": "application/json",
            "headers": [
                {"name": "Authorization", "type": "string", "required": True, "desc": "Bearer <YOUR_API_KEY>"},
                {"name": "Content-Type", "type": "string", "required": True, "desc": "application/json"}
            ],
            "parameters": [
                {"name": "model", "type": "string", "required": True, "desc": "embed-standard"},
                {"name": "input", "type": "string | array", "required": True, "desc": "Chuỗi văn bản hoặc mảng chuỗi cần trích xuất vector"}
            ],
            "sample_response": '{\n  "object": "list",\n  "data": [{\n    "object": "embedding",\n    "index": 0,\n    "embedding": [-0.012, 0.045, -0.078, ...]\n  }],\n  "model": "embed-standard",\n  "usage": { "prompt_tokens": 8, "total_tokens": 8 }\n}'
        },
        "pricing": {
            "free_quota": "100,000 tokens miễn phí mỗi tháng",
            "pay_as_you_go": "2 VNĐ / 1,000 tokens",
            "billing_cycle": "Thanh toán dựa trên số lượng tokens trích xuất vector"
        }
    },
    {
        "endpoint_id": "/v1/nlp/translation",
        "path": "/v1/nlp/translation",
        "method": "POST",
        "api_id": "api_translation",
        "name": "Translation API",
        "category": "Natural Language Processing",
        "status": "active",
        "description": "Bidirectional Vietnamese - English machine translation API.",
        "icon": "fa-language",
        "free_quota": "100,000 characters",
        "unit": "character",
        "overview": {
            "title": "Vietnamese - English Neural Machine Translation",
            "summary": "Dịch thuật văn bản tự động chính xác cao giữa tiếng Việt và tiếng Anh dựa trên mô hình Helsinki-NLP OPUS.",
            "features": [
                "Dịch hai chiều: Tiếng Việt sang Tiếng Anh (vi -> en) và Tiếng Anh sang Tiếng Việt (en -> vi)",
                "Bảo toàn ngữ cảnh và thuật ngữ chuyên ngành",
                "Tốc độ xử lý siêu nhanh dưới 50ms cho câu thông thường",
                "Dễ dàng tích hợp vào ứng dụng đa ngôn ngữ"
            ]
        },
        "document": {
            "endpoint_url": "http://localhost:8000/v1/nlp/translation",
            "method": "POST",
            "content_type": "application/json",
            "headers": [
                {"name": "Authorization", "type": "string", "required": True, "desc": "Bearer <YOUR_API_KEY>"},
                {"name": "Content-Type", "type": "string", "required": True, "desc": "application/json"}
            ],
            "parameters": [
                {"name": "text", "type": "string", "required": True, "desc": "Đoạn văn bản cần dịch"},
                {"name": "source_lang", "type": "string", "required": False, "desc": "vi hoặc en (mặc định: vi)"},
                {"name": "target_lang", "type": "string", "required": False, "desc": "en hoặc vi (mặc định: en)"}
            ],
            "sample_response": '{\n  "status": "success",\n  "source_lang": "vi",\n  "target_lang": "en",\n  "original_text": "Xin chào!",\n  "translated_text": "Hello!"\n}'
        },
        "pricing": {
            "free_quota": "100,000 ký tự miễn phí mỗi tháng",
            "pay_as_you_go": "15 VNĐ / 1,000 ký tự",
            "billing_cycle": "Thanh toán dựa trên số lượng ký tự dịch thuật"
        }
    }
]


class MongoEndpointRepository(IEndpointRepository):
    """MongoDB Atlas implementation for Endpoints serving as full API Catalog."""

    def __init__(self):
        self._endpoints_cache: Dict[str, Dict[str, Any]] = {}

    async def list_endpoints(self) -> Dict[str, Any]:
        db = mongo_manager.get_database()
        if db is not None:
            try:
                cursor = db.endpoints.find({}, {"_id": 0})
                eps = await cursor.to_list(length=100)

                # Auto-seed if empty
                if not eps or len(eps) == 0:
                    await db.endpoints.insert_many([dict(e) for e in DEFAULT_ENDPOINTS])
                    cursor = db.endpoints.find({}, {"_id": 0})
                    eps = await cursor.to_list(length=100)

                self._endpoints_cache.clear()
                for item in eps:
                    item.pop("_id", None)
                    self._endpoints_cache[item["endpoint_id"]] = item
                return self._endpoints_cache
            except Exception:
                pass

        # Fallback to defaults if DB completely fails
        if not self._endpoints_cache:
            self._endpoints_cache = {e["endpoint_id"]: dict(e) for e in DEFAULT_ENDPOINTS}
        return self._endpoints_cache

    async def update_endpoint_status(self, endpoint_id: str, status: str) -> Optional[Dict[str, Any]]:
        db = mongo_manager.get_database()
        if db is not None:
            try:
                await db.endpoints.update_one({"endpoint_id": endpoint_id}, {"$set": {"status": status}})
            except Exception:
                pass

        if endpoint_id in self._endpoints_cache:
            self._endpoints_cache[endpoint_id]["status"] = status
            return self._endpoints_cache[endpoint_id]
        return None


endpoint_repository = MongoEndpointRepository()
