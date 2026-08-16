from typing import Optional, Dict, Any
from common.interfaces.endpoints import IEndpointRepository
from common.database.mongodb import mongo_manager

DEFAULT_ENDPOINTS = [
    {
        "endpoint_id": "/v1/chat/completions",
        "api_id": "api_llm",
        "name": "LLM Chatbot API",
        "category": "Generative AI",
        "status": "active",
        "description": "Standard OpenAI-compatible Chat completion interface based on Qwen3-14B & DeepSeek V3.",
        "icon": "fa-robot",
        "free_quota": "50,000 tokens",
        "unit": "token",
        "overview": {
            "title": "Qwen3 & DeepSeek V3 Generative AI Engine",
            "summary": "Mô hình ngôn ngữ lớn thế hệ mới tối ưu cho tiếng Việt, có khả năng suy luận logic, trả lời câu hỏi và viết mã lập trình chuyên nghiệp.",
            "features": [
                "Mô hình Qwen3-14B & DeepSeek V3 671B thông minh hàng đầu",
                "Hỗ trợ context window lớn đến 64,000 tokens",
                "Khả năng đọc hiểu tài liệu, trích xuất thông tin và tạo báo cáo",
                "Chuẩn RESTful API tương thích 100% với OpenAI SDK"
            ]
        },
        "document": {
            "endpoint_url": "https://ai-platform-6p72.onrender.com/v1/chat/completions",
            "method": "POST",
            "content_type": "application/json",
            "headers": [
                {"name": "api-key", "type": "string", "required": True, "desc": "Khóa API Key của bạn"},
                {"name": "Content-Type", "type": "string", "required": True, "desc": "application/json"}
            ],
            "parameters": [
                {"name": "model", "type": "string", "required": True, "desc": "deepseek-v3 hoặc qwen3-14b"},
                {"name": "messages", "type": "array", "required": True, "desc": "Danh sách tin nhắn hội thoại role/content"}
            ],
            "sample_response": '{\n  "id": "chatcmpl-99812",\n  "choices": [{\n    "message": {\n      "role": "assistant",\n      "content": "Xin chào! Tôi có thể giúp gì cho bạn hôm nay?"\n    }\n  }],\n  "usage": { "total_tokens": 32 }\n}'
        },
        "pricing": {
            "free_quota": "50,000 tokens miễn phí mỗi tháng",
            "pay_as_you_go": "10 VNĐ / 1,000 tokens",
            "billing_cycle": "Thanh toán dựa trên tổng Input + Output Tokens"
        }
    },
    {
        "endpoint_id": "/v1/audio/transcriptions",
        "api_id": "api_stt",
        "name": "Speech to Text API",
        "category": "Speech Recognition",
        "status": "active",
        "description": "PhoWhisper ASR Speech-to-Text inference endpoint",
        "icon": "fa-microphone",
        "free_quota": "10,000 blocks",
        "unit": "block",
        "overview": {
            "title": "PhoWhisper Speech-to-Text Large v3 Engine",
            "summary": "Speech synthesis & recognition is the fundamental component of modern artificial intelligence systems. With high ambition, Everwin Technology Innovation Department has launched Everwin AI Speech Synthesis & PhoWhisper ASR.",
            "features": [
                "Building automatic communication system: automated call center, serving machine, maid robot",
                "Enhance user's experience: reading content for users when unable to monitor screen",
                "Service for language interaction for visually impaired people"
            ]
        },
        "document": {
            "endpoint_url": "https://ai-platform-6p72.onrender.com/v1/audio/transcriptions",
            "method": "POST",
            "content_type": "multipart/form-data",
            "headers": [
                {"name": "api-key", "type": "string", "required": True, "desc": "Khóa API Key khởi tạo từ Console"}
            ],
            "parameters": [
                {"name": "file", "type": "file", "required": True, "desc": "File âm thanh định dạng WAV/MP3/FLAC"},
                {"name": "model", "type": "string", "required": False, "desc": "Tên mô hình (mặc định: PhoWhisper-STT-v1)"}
            ],
            "sample_response": '{\n  "text": "Xin chào Everwin AI Platform! Đây là kết quả nhận dạng giọng nói PhoWhisper STT.",\n  "language": "vi",\n  "duration": 3.42,\n  "confidence": 0.985\n}'
        },
        "pricing": {
            "free_quota": "10,000 blocks miễn phí mỗi tháng",
            "pay_as_you_go": "150 VNĐ / block (1 block = 15 giây âm thanh)",
            "billing_cycle": "Thanh toán theo mức sử dụng thực tế (Pay-as-you-go)"
        }
    },
    {
        "endpoint_id": "/v1/audio/speech",
        "api_id": "api_tts",
        "name": "Text to Speech API",
        "category": "Speech Synthesis",
        "status": "active",
        "description": "VieTTS Text-to-Speech synthesis endpoint",
        "icon": "fa-volume-high",
        "free_quota": "100,000 characters",
        "unit": "character",
        "overview": {
            "title": "FPT.AI Speech - Text to Speech",
            "summary": "Speech synthesis is the fundamental component of many artificial intelligence systems. With our own ambition, FPT Technology Innovation Department has launched FPT Speech Synthesis. Being considered as the best integrated system of Vietnamese language voice in the market today.",
            "features": [
                "Building automatic communication system: automated call center, serving machine, maid robot",
                "Enhance user's experience: reading content for users when unable to monitor screen, book reading apps",
                "Service for language interaction for visually impaired people"
            ]
        },
        "document": {
            "endpoint_url": "https://api.fpt.ai/hmi/tts/v5",
            "method": "POST",
            "content_type": "application/json",
            "headers": [
                {"name": "api_key", "type": "string", "required": True, "desc": "Your API key (get from console.fpt.ai)"},
                {"name": "voice", "type": "string", "required": False, "desc": "banmai (female northern), lannhi (female southern), leminh (male northern), myan (female middle)"},
                {"name": "speed", "type": "number", "required": False, "desc": "Adjust speed of voice (-3 slowest to +3 fastest, default 0)"},
                {"name": "format", "type": "string", "required": False, "desc": "Output format: mp3 or wav (default mp3)"},
                {"name": "callback_url", "type": "string", "required": False, "desc": "URL provided by customer to receive async notification"}
            ],
            "parameters": [
                {"name": "body", "type": "string", "required": True, "desc": "Text content to convert (Limit: 3 to 5,000 characters per request)"}
            ],
            "sample_response": '{\n  "async": "https://s3-ap-southeast-1.amazonaws.com/text2speech-v4/male.0.pro.4b5b15285847e83acbb3beb945434453.mp3",\n  "error": 0,\n  "message": "The content will be returned after a few seconds under the async link.",\n  "request_id": "4b5b15285847e83acbb3beb945434453"\n}'
        },
        "pricing": {
            "free_quota": "Free Tier: 100,000 characters / month (Low speed, queued requests)",
            "pay_as_you_go": "Premium Pack 1,500,000 chars (500k VNĐ) | 4,000,000 chars (1M VNĐ) | 10,000,000 chars (2M VNĐ)",
            "billing_cycle": "Business Premium: Unlimited speed & usage time with standard technical support"
        }
    },
    {
        "endpoint_id": "/v1/images/generations",
        "api_id": "api_image",
        "name": "Image Generation API",
        "category": "Generative AI",
        "status": "active",
        "description": "DALL-E 3 & Flux compatible endpoint for generating high quality images from text prompts.",
        "icon": "fa-image",
        "free_quota": "100 images",
        "unit": "image",
        "overview": {
            "title": "Flux & SDXL Image Generator",
            "summary": "Tạo ảnh chất lượng cao từ văn bản với các mô hình Diffusion hàng đầu.",
            "features": [
                "Độ phân giải siêu cao 4K",
                "Hỗ trợ prompt tiếng Việt",
                "Tốc độ tạo ảnh nhanh dưới 2s"
            ]
        },
        "document": {
            "endpoint_url": "https://ai-platform-6p72.onrender.com/v1/images/generations",
            "method": "POST",
            "content_type": "application/json",
            "headers": [
                {"name": "api-key", "type": "string", "required": True, "desc": "Khóa API Key"}
            ],
            "parameters": [
                {"name": "prompt", "type": "string", "required": True, "desc": "Mô tả bức ảnh cần tạo"},
                {"name": "size", "type": "string", "required": False, "desc": "Kích thước ảnh (1024x1024)"}
            ],
            "sample_response": '{\n  "data": [{\n    "url": "https://ai-platform-6p72.onrender.com/images/xyz.png"\n  }]\n}'
        },
        "pricing": {
            "free_quota": "100 ảnh miễn phí",
            "pay_as_you_go": "200 VNĐ / ảnh",
            "billing_cycle": "Thanh toán theo số lượng ảnh tạo thành công"
        }
    },
    {
        "endpoint_id": "/v1/moderation/text",
        "api_id": "api_moderation",
        "name": "Content Moderation API",
        "category": "Trust & Safety",
        "status": "active",
        "description": "AI Content Safety & Toxic Filter endpoint to detect violence, hate speech, and harassment.",
        "icon": "fa-shield-halved",
        "free_quota": "10,000 requests",
        "unit": "request",
        "overview": {
            "title": "Vietnamese Text Moderation Filter",
            "summary": "Bộ lọc nội dung độc hại chuyên biệt cho tiếng Việt, bảo vệ nền tảng của bạn khỏi các nội dung bạo lực (violence), thù ghét.",
            "features": [
                "Phát hiện bạo lực, thù ghét, quấy rối",
                "Tốc độ xử lý siêu nhanh <50ms",
                "Độ chính xác lên tới 99% cho tiếng Việt"
            ]
        },
        "document": {
            "endpoint_url": "https://ai-platform-6p72.onrender.com/v1/moderation/text",
            "method": "POST",
            "content_type": "application/json",
            "headers": [
                {"name": "api-key", "type": "string", "required": True, "desc": "Khóa API Key"}
            ],
            "parameters": [
                {"name": "input", "type": "string", "required": True, "desc": "Văn bản cần kiểm duyệt"}
            ],
            "sample_response": '{\n  "results": [{\n    "flagged": true,\n    "categories": {"violence": true, "hate": false}\n  }]\n}'
        },
        "pricing": {
            "free_quota": "10,000 requests miễn phí",
            "pay_as_you_go": "10 VNĐ / request",
            "billing_cycle": "Thanh toán theo lượng request"
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
