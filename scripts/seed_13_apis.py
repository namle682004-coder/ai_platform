import asyncio
import sys

# Add packages and services to sys.path
sys.path.insert(0, '/home/namle/AI-Projects/llm-apps/ai_platform/packages')
sys.path.insert(0, '/home/namle/AI-Projects/llm-apps/ai_platform/services/gateway')

from common.database.mongodb import mongo_manager

NEW_ENDPOINTS = [
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
            "summary": "Speech synthesis & recognition is the fundamental component of modern artificial intelligence systems.",
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
            "summary": "Speech synthesis is the fundamental component of many artificial intelligence systems.",
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
                {"name": "voice", "type": "string", "required": False, "desc": "banmai, lannhi, leminh, myan"},
                {"name": "speed", "type": "number", "required": False, "desc": "Adjust speed (-3 to +3)"}
            ],
            "parameters": [
                {"name": "body", "type": "string", "required": True, "desc": "Text content to convert (Limit: 5,000 characters)"}
            ],
            "sample_response": '{\n  "async": "https://s3-ap-southeast-1.amazonaws.com/text2speech/male.mp3",\n  "error": 0,\n  "request_id": "4b5b15285847e83acbb3beb945434453"\n}'
        },
        "pricing": {
            "free_quota": "Free Tier: 100,000 characters / month",
            "pay_as_you_go": "Premium Pack: 250 VNĐ / 1,000 characters",
            "billing_cycle": "Business Premium: Unlimited speed & usage time"
        }
    },
    {
        "endpoint_id": "/v1/images/generations",
        "api_id": "api_image",
        "name": "Image Generation API",
        "category": "Generative AI",
        "status": "active",
        "description": "DALL-E 3 & Flux compatible endpoint for generating high quality images.",
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
            "summary": "Bộ lọc nội dung độc hại chuyên biệt cho tiếng Việt.",
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
    },
    {
        "endpoint_id": "/v1/ocr/driver-license",
        "api_id": "api_ocr_dl",
        "name": "Driver's license recognition",
        "category": "OCR & Reader",
        "status": "disabled",
        "description": "Extract rich information from driver's license cards using advanced AI OCR.",
        "icon": "fa-id-card-clip",
        "free_quota": "1,000 requests",
        "unit": "request",
        "overview": {
            "title": "Driver's License OCR Recognition",
            "summary": "Tự động trích xuất các thông tin trên Giấy phép lái xe như Số GPLX, Họ tên, Hạng, Ngày trúng tuyển...",
            "features": [
                "Độ chính xác số và tên lên tới 98%",
                "Hỗ trợ cả mẫu GPLX thẻ nhựa (PET) và thẻ giấy cũ",
                "Tự động xoay ảnh và hiệu chỉnh độ nghiêng"
            ]
        },
        "document": {
            "endpoint_url": "https://ai-platform-6p72.onrender.com/v1/ocr/driver-license",
            "method": "POST",
            "content_type": "multipart/form-data",
            "headers": [
                {"name": "api-key", "type": "string", "required": True, "desc": "Khóa API Key"}
            ],
            "parameters": [
                {"name": "image", "type": "file", "required": True, "desc": "Ảnh chụp giấy phép lái xe"}
            ],
            "sample_response": '{\n  "status": "success",\n  "data": {\n    "license_number": "120398401923",\n    "full_name": "NGUYEN VAN A",\n    "class": "A1"\n  }\n}'
        },
        "pricing": {
            "free_quota": "1,000 requests miễn phí",
            "pay_as_you_go": "250 VNĐ / request",
            "billing_cycle": "Thanh toán dựa trên số lượt gọi thành công"
        }
    },
    {
        "endpoint_id": "/v1/ocr/id-card",
        "api_id": "api_ocr_id",
        "name": "ID Recognition",
        "category": "OCR & Reader",
        "status": "disabled",
        "description": "Extract rich information from citizen identity cards (CCCD/CMND) with high accuracy.",
        "icon": "fa-address-card",
        "free_quota": "1,000 requests",
        "unit": "request",
        "overview": {
            "title": "ID Card OCR Recognition (CCCD/CMND)",
            "summary": "Tự động trích xuất đầy đủ thông tin mặt trước và mặt sau của CMND 9 số, 12 số và CCCD gắn chíp.",
            "features": [
                "Nhận diện Số định danh cá nhân, Họ tên, Ngày sinh, Địa chỉ, Ngày cấp, Nơi cấp",
                "Tự động phát hiện thẻ bị cắt góc, chụp nghiêng hoặc giả mạo",
                "Xử lý nhanh dưới 200ms"
            ]
        },
        "document": {
            "endpoint_url": "https://ai-platform-6p72.onrender.com/v1/ocr/id-card",
            "method": "POST",
            "content_type": "multipart/form-data",
            "headers": [
                {"name": "api-key", "type": "string", "required": True, "desc": "Khóa API Key"}
            ],
            "parameters": [
                {"name": "image", "type": "file", "required": True, "desc": "Ảnh chụp mặt trước hoặc mặt sau CCCD"}
            ],
            "sample_response": '{\n  "status": "success",\n  "data": {\n    "id_number": "001095012345",\n    "full_name": "TRAN THI B",\n    "dob": "15/08/1995"\n  }\n}'
        },
        "pricing": {
            "free_quota": "1,000 requests miễn phí",
            "pay_as_you_go": "200 VNĐ / request",
            "billing_cycle": "Thanh toán dựa trên số lượt gọi"
        }
    },
    {
        "endpoint_id": "/v1/ocr/passport",
        "api_id": "api_ocr_passport",
        "name": "Passport Recognition",
        "category": "OCR & Reader",
        "status": "disabled",
        "description": "Extract structured information from passport document images.",
        "icon": "fa-passport",
        "free_quota": "1,000 requests",
        "unit": "request",
        "overview": {
            "title": "Passport OCR Recognition",
            "summary": "Tự động quét và đọc dòng MRZ (Machine Readable Zone) trên Hộ chiếu để trích xuất thông tin khách hàng.",
            "features": [
                "Hỗ trợ hộ chiếu Việt Nam và hộ chiếu quốc tế ICAO-compliant",
                "Đọc chính xác Số hộ chiếu, Quốc tịch, Họ tên, Số định danh, Ngày hết hạn",
                "Nhận diện chính xác 99.8% dòng MRZ"
            ]
        },
        "document": {
            "endpoint_url": "https://ai-platform-6p72.onrender.com/v1/ocr/passport",
            "method": "POST",
            "content_type": "multipart/form-data",
            "headers": [
                {"name": "api-key", "type": "string", "required": True, "desc": "Khóa API Key"}
            ],
            "parameters": [
                {"name": "image", "type": "file", "required": True, "desc": "Ảnh chụp trang thông tin hộ chiếu"}
            ],
            "sample_response": '{\n  "status": "success",\n  "data": {\n    "passport_number": "B1234567",\n    "nationality": "VNM",\n    "full_name": "PHAM VAN C"\n  }\n}'
        },
        "pricing": {
            "free_quota": "1,000 requests miễn phí",
            "pay_as_you_go": "300 VNĐ / request",
            "billing_cycle": "Thanh toán dựa trên số lượt gọi"
        }
    },
    {
        "endpoint_id": "/v1/vision/facematch",
        "api_id": "api_vision_facematch",
        "name": "FaceMatch",
        "category": "Computer Vision",
        "status": "active",
        "description": "Compare two face images to verify if they belong to the same individual.",
        "icon": "fa-user-check",
        "free_quota": "1,000 requests",
        "unit": "request",
        "overview": {
            "title": "FaceMatch eKYC Engine",
            "summary": "So khớp khuôn mặt giữa ảnh chân dung CCCD và ảnh selfie thực tế để phát hiện trùng khớp sinh trắc học.",
            "features": [
                "Sử dụng thuật toán ArcFace tối tân",
                "Độ chính xác vượt trội ngay cả khi thay đổi kiểu tóc, kính mắt hoặc ánh sáng",
                "Trả về tỷ lệ phần trăm khớp (confidence score)"
            ]
        },
        "document": {
            "endpoint_url": "https://ai-platform-6p72.onrender.com/v1/vision/facematch",
            "method": "POST",
            "content_type": "multipart/form-data",
            "headers": [
                {"name": "api-key", "type": "string", "required": True, "desc": "Khóa API Key"}
            ],
            "parameters": [
                {"name": "image_cccd", "type": "file", "required": True, "desc": "Ảnh chân dung trên thẻ CCCD"},
                {"name": "image_selfie", "type": "file", "required": True, "desc": "Ảnh selfie chụp thực tế"}
            ],
            "sample_response": '{\n  "status": "success",\n  "matched": true,\n  "confidence": 0.942\n}'
        },
        "pricing": {
            "free_quota": "1,000 requests miễn phí",
            "pay_as_you_go": "350 VNĐ / request",
            "billing_cycle": "Thanh toán theo lượt đối khớp"
        }
    },
    {
        "endpoint_id": "/v1/vision/liveness-v3",
        "api_id": "api_vision_liveness",
        "name": "Liveness v3",
        "category": "Computer Vision",
        "status": "disabled",
        "description": "FPT.AI Reader - Liveness Detection v3 to prevent spoofing attacks.",
        "icon": "fa-user-shield",
        "free_quota": "500 requests",
        "unit": "request",
        "overview": {
            "title": "Liveness Detection v3",
            "summary": "Xác thực thực thể khuôn mặt (chống giả mạo sinh trắc học) bằng cách phân tích ảnh hoặc video selfie.",
            "features": [
                "Phát hiện giả mạo qua màn hình điện thoại, ảnh in giấy hoặc mặt nạ silicon",
                "Hỗ trợ cả cơ chế Active Liveness (nháy mắt, quay đầu) và Passive Liveness (ảnh tĩnh)",
                "Đạt tiêu chuẩn bảo mật ngân hàng"
            ]
        },
        "document": {
            "endpoint_url": "https://ai-platform-6p72.onrender.com/v1/vision/liveness-v3",
            "method": "POST",
            "content_type": "multipart/form-data",
            "headers": [
                {"name": "api-key", "type": "string", "required": True, "desc": "Khóa API Key"}
            ],
            "parameters": [
                {"name": "video", "type": "file", "required": True, "desc": "Video ngắn quay khuôn mặt cử động"},
                {"name": "mode", "type": "string", "required": False, "desc": "passive hoặc active"}
            ],
            "sample_response": '{\n  "status": "success",\n  "is_live": true,\n  "score": 0.991\n}'
        },
        "pricing": {
            "free_quota": "500 requests miễn phí",
            "pay_as_you_go": "450 VNĐ / request",
            "billing_cycle": "Thanh toán dựa trên số lượt gọi"
        }
    },
    {
        "endpoint_id": "/v1/nlp/embeddings",
        "api_id": "api_nlp_embeddings",
        "name": "Text Embedding API",
        "category": "Natural Language Processing",
        "status": "active",
        "description": "Generate dense vector representations for text inputs, ideal for semantic search.",
        "icon": "fa-magnifying-glass",
        "free_quota": "50,000 sentences",
        "unit": "sentence",
        "overview": {
            "title": "Multilingual Text Embeddings",
            "summary": "Biến đổi câu hoặc đoạn văn bản thành vector 768 chiều phục vụ tìm kiếm ngữ nghĩa và RAG nội bộ.",
            "features": [
                "Dựa trên mô hình E5 Multilingual chất lượng cao",
                "Hỗ trợ xuất sắc cho tiếng Việt và tiếng Anh",
                "Thích hợp lưu trữ vào Pinecone, Milvus, Qdrant"
            ]
        },
        "document": {
            "endpoint_url": "https://ai-platform-6p72.onrender.com/v1/nlp/embeddings",
            "method": "POST",
            "content_type": "application/json",
            "headers": [
                {"name": "api-key", "type": "string", "required": True, "desc": "Khóa API Key"}
            ],
            "parameters": [
                {"name": "text", "type": "string", "required": True, "desc": "Đoạn văn bản cần nhúng (Embedding)"}
            ],
            "sample_response": '{\n  "object": "list",\n  "data": [{\n    "embedding": [0.012, -0.043, 0.089, "..."],\n    "index": 0\n  }]\n}'
        },
        "pricing": {
            "free_quota": "50,000 câu miễn phí mỗi tháng",
            "pay_as_you_go": "5 VNĐ / 1,000 câu",
            "billing_cycle": "Thanh toán theo lượng câu được nhúng"
        }
    },
    {
        "endpoint_id": "/v1/nlp/summarization",
        "api_id": "api_nlp_summarization",
        "name": "Text Summarization API",
        "category": "Natural Language Processing",
        "status": "active",
        "description": "Summarize long articles or documents into concise bullet points.",
        "icon": "fa-file-lines",
        "free_quota": "10,000 requests",
        "unit": "request",
        "overview": {
            "title": "Vietnamese Text Summarizer",
            "summary": "Tự động tóm tắt các tài liệu, báo cáo, bài báo tiếng Việt dài thành đoạn tóm tắt ngắn gọn súc tích.",
            "features": [
                "Tùy chỉnh độ dài đoạn tóm tắt",
                "Giữ nguyên các từ khóa và nội dung cốt lõi của văn bản",
                "Dựa trên mô hình BARTpho-syllable chuyên sâu tiếng Việt"
            ]
        },
        "document": {
            "endpoint_url": "https://ai-platform-6p72.onrender.com/v1/nlp/summarization",
            "method": "POST",
            "content_type": "application/json",
            "headers": [
                {"name": "api-key", "type": "string", "required": True, "desc": "Khóa API Key"}
            ],
            "parameters": [
                {"name": "document", "type": "string", "required": True, "desc": "Nội dung văn bản dài cần tóm tắt"},
                {"name": "ratio", "type": "number", "required": False, "desc": "Tỷ lệ tóm tắt (mặc định: 0.2)"}
            ],
            "sample_response": '{\n  "status": "success",\n  "summary": "Everwin AI Platform ra mắt bộ 13 API dịch vụ trí tuệ nhân tạo thế hệ mới tích hợp sâu rộng..."\n}'
        },
        "pricing": {
            "free_quota": "10,000 requests miễn phí",
            "pay_as_you_go": "50 VNĐ / request",
            "billing_cycle": "Thanh toán theo lượt tóm tắt"
        }
    },
    {
        "endpoint_id": "/v1/nlp/translation",
        "api_id": "api_nlp_translation",
        "name": "Translation API",
        "category": "Natural Language Processing",
        "status": "active",
        "description": "High-quality machine translation between English and Vietnamese.",
        "icon": "fa-language",
        "free_quota": "100,000 characters",
        "unit": "character",
        "overview": {
            "title": "English-Vietnamese Translation Engine",
            "summary": "Dịch thuật hai chiều Anh - Việt độ chính xác cao chuyên biệt cho văn bản hành chính, kỹ thuật và đối thoại.",
            "features": [
                "Dựa trên mô hình ViT5 tối tân cho tiếng Việt",
                "Dịch mượt mà, đúng ngữ cảnh và văn phong bản địa",
                "Hỗ trợ dịch tài liệu số lượng lớn"
            ]
        },
        "document": {
            "endpoint_url": "https://ai-platform-6p72.onrender.com/v1/nlp/translation",
            "method": "POST",
            "content_type": "application/json",
            "headers": [
                {"name": "api-key", "type": "string", "required": True, "desc": "Khóa API Key"}
            ],
            "parameters": [
                {"name": "text", "type": "string", "required": True, "desc": "Văn bản cần dịch"},
                {"name": "source_lang", "type": "string", "required": True, "desc": "vi hoặc en"},
                {"name": "target_lang", "type": "string", "required": True, "desc": "en hoặc vi"}
            ],
            "sample_response": '{\n  "status": "success",\n  "translated_text": "Welcome to Everwin AI Platform."\n}'
        },
        "pricing": {
            "free_quota": "100,000 ký tự miễn phí",
            "pay_as_you_go": "50 VNĐ / 1,000 ký tự",
            "billing_cycle": "Thanh toán theo lượng ký tự dịch thuật thực tế"
        }
    }
]

async def seed_13_apis():
    await mongo_manager.connect()
    db = mongo_manager.get_database()
    if db is None:
        print("Error: Could not connect to MongoDB Atlas.")
        return

    # Delete existing endpoints
    await db.endpoints.delete_many({})
    print("Cleared existing endpoints collection.")

    # Insert 13 new APIs
    result = await db.endpoints.insert_many(NEW_ENDPOINTS)
    print(f"Successfully inserted {len(result.inserted_ids)} API endpoints into MongoDB Atlas!")

if __name__ == "__main__":
    asyncio.run(seed_13_apis())
