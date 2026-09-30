from typing import Optional, Dict, Any, List
from common.interfaces.endpoints import IEndpointRepository
from common.database.mongodb import mongo_manager

DEFAULT_ENDPOINTS: List[Dict[str, Any]] = [
    {
        "id": "efb24a03-059d-440c-bd35-0b5b3a776983",
        "api_id": "api_llm",
        "endpoint_id": "/v1/chat/completions",
        "path": "/v1/chat/completions",
        "method": "POST",
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
        "id": "3a72d1f9-46c8-472e-8395-cb091a136701",
        "api_id": "api_stt",
        "endpoint_id": "/v1/audio/transcriptions",
        "path": "/v1/audio/transcriptions",
        "method": "POST",
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
        "id": "8b51ef94-912a-4367-bf16-36701a09cb12",
        "api_id": "api_tts",
        "endpoint_id": "/v1/audio/speech",
        "path": "/v1/audio/speech",
        "method": "POST",
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
                "Hỗ trợ 4 giọng đọc chuẩn: banmai, leminh, lannhi, namminh",
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
        "id": "c194a2b3-5710-4821-9472-a08361b09234",
        "api_id": "api_ocr_id",
        "endpoint_id": "/v1/ocr/id-card",
        "path": "/v1/ocr/id-card",
        "method": "POST",
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
        "id": "a5b8e6f7-9154-4c65-d816-e42705f43678",
        "api_id": "api_moderation",
        "endpoint_id": "/v1/moderations",
        "path": "/v1/moderations",
        "method": "POST",
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
        "id": "d8eb19ca-2487-4f98-0b49-175038c76901",
        "api_id": "api_embeddings",
        "endpoint_id": "/v1/embeddings",
        "path": "/v1/embeddings",
        "method": "POST",
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
            "sample_response": '{\n  "object": "list",\n  "data": [{\n    "object": "embedding",\n    "index": 0,\n    "embedding": [-0.012, 0.045, -0.078]\n  }],\n  "model": "embed-standard",\n  "usage": { "prompt_tokens": 8, "total_tokens": 8 }\n}'
        },
        "pricing": {
            "free_quota": "100,000 tokens miễn phí mỗi tháng",
            "pay_as_you_go": "2 VNĐ / 1,000 tokens",
            "billing_cycle": "Thanh toán dựa trên số lượng tokens trích xuất vector"
        }
    },
    {
        "id": "e9fc2adb-3598-40a9-1c5a-286149d87012",
        "api_id": "api_translation",
        "endpoint_id": "/v1/nlp/translation",
        "path": "/v1/nlp/translation",
        "method": "POST",
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
    },
    {
        "id": "f4a7d5e6-8043-4b54-c705-d31694e32567",
        "api_id": "api_image",
        "endpoint_id": "/v1/images/generations",
        "path": "/v1/images/generations",
        "method": "POST",
        "name": "Image Generation API",
        "category": "Generative AI",
        "status": "active",
        "description": "Text-to-image generation powered by FLUX.1 & Stable Diffusion XL.",
        "icon": "fa-image",
        "free_quota": "100 images",
        "unit": "image",
        "overview": {
            "title": "Flux & SDXL Image Generator",
            "summary": "Tạo ảnh nghệ thuật và thiết kế chất lượng cao từ mô tả văn bản.",
            "features": [
                "Độ phân giải chân thực cao",
                "Hỗ trợ prompt tiếng Việt & tiếng Anh",
                "Tốc độ sinh ảnh tối ưu"
            ]
        },
        "document": {
            "endpoint_url": "http://localhost:8000/v1/images/generations",
            "method": "POST",
            "content_type": "application/json",
            "headers": [
                {"name": "Authorization", "type": "string", "required": True, "desc": "Bearer <YOUR_API_KEY>"},
                {"name": "Content-Type", "type": "string", "required": True, "desc": "application/json"}
            ],
            "parameters": [
                {"name": "prompt", "type": "string", "required": True, "desc": "Mô tả bức ảnh cần tạo"},
                {"name": "size", "type": "string", "required": False, "desc": "Kích thước ảnh (1024x1024)"}
            ],
            "sample_response": '{\n  "data": [{"url": "http://localhost:8000/images/sample.png"}]\n}'
        },
        "pricing": {
            "free_quota": "100 ảnh miễn phí",
            "pay_as_you_go": "200 VNĐ / ảnh",
            "billing_cycle": "Thanh toán theo số lượng ảnh tạo thành công"
        }
    },
    {
        "id": "d285b3c4-6821-4932-a583-b19472c10345",
        "api_id": "api_ocr_dl",
        "endpoint_id": "/v1/ocr/driver-license",
        "path": "/v1/ocr/driver-license",
        "method": "POST",
        "name": "Driver's license recognition",
        "category": "OCR & Reader",
        "status": "active",
        "description": "Extract rich information from driver's license cards using advanced AI OCR.",
        "icon": "fa-id-card-clip",
        "free_quota": "1,000 requests",
        "unit": "request",
        "overview": {
            "title": "Driver's License OCR Recognition",
            "summary": "Tự động trích xuất các thông tin trên Giấy phép lái xe như Số GPLX, Họ tên, Hạng, Ngày trúng tuyển.",
            "features": [
                "Độ chính xác cao cho thẻ nhựa (PET) và giấy",
                "Tự động xoay ảnh và hiệu chỉnh độ nghiêng",
                "Chuẩn hóa dữ liệu trả về"
            ]
        },
        "document": {
            "endpoint_url": "http://localhost:8000/v1/ocr/driver-license",
            "method": "POST",
            "content_type": "multipart/form-data",
            "headers": [
                {"name": "Authorization", "type": "string", "required": True, "desc": "Bearer <YOUR_API_KEY>"}
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
        "id": "e396c4d5-7932-4a43-b694-c20583d21456",
        "api_id": "api_ocr_passport",
        "endpoint_id": "/v1/ocr/passport",
        "path": "/v1/ocr/passport",
        "method": "POST",
        "name": "Passport Recognition",
        "category": "OCR & Reader",
        "status": "active",
        "description": "Extract structured information from passport document images.",
        "icon": "fa-passport",
        "free_quota": "1,000 requests",
        "unit": "request",
        "overview": {
            "title": "Passport OCR Recognition",
            "summary": "Tự động quét và đọc dòng MRZ (Machine Readable Zone) trên Hộ chiếu để trích xuất thông tin khách hàng.",
            "features": [
                "Hỗ trợ hộ chiếu Việt Nam và quốc tế ICAO-compliant",
                "Đọc chính xác Số hộ chiếu, Quốc tịch, Họ tên",
                "Nhận diện chính xác dòng MRZ"
            ]
        },
        "document": {
            "endpoint_url": "http://localhost:8000/v1/ocr/passport",
            "method": "POST",
            "content_type": "multipart/form-data",
            "headers": [
                {"name": "Authorization", "type": "string", "required": True, "desc": "Bearer <YOUR_API_KEY>"}
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
        "id": "b6c9f7a8-0265-4d76-e927-f53816a54789",
        "api_id": "api_vision_facematch",
        "endpoint_id": "/v1/vision/facematch",
        "path": "/v1/vision/facematch",
        "method": "POST",
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
                "Thuật toán đối chiếu đặc trưng khuôn mặt tối tân",
                "Độ chính xác cao vượt trội",
                "Trả về tỷ lệ phần trăm khớp (confidence score)"
            ]
        },
        "document": {
            "endpoint_url": "http://localhost:8000/v1/vision/facematch",
            "method": "POST",
            "content_type": "multipart/form-data",
            "headers": [
                {"name": "Authorization", "type": "string", "required": True, "desc": "Bearer <YOUR_API_KEY>"}
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
        "id": "c7da08b9-1376-4e87-fa38-064927b65890",
        "api_id": "api_vision_liveness",
        "endpoint_id": "/v1/vision/liveness-v3",
        "path": "/v1/vision/liveness-v3",
        "method": "POST",
        "name": "Liveness v3",
        "category": "Computer Vision",
        "status": "active",
        "description": "Advanced Liveness Detection v3 to prevent biometric spoofing attacks.",
        "icon": "fa-user-shield",
        "free_quota": "500 requests",
        "unit": "request",
        "overview": {
            "title": "Liveness Detection v3",
            "summary": "Xác thực thực thể khuôn mặt (chống giả mạo sinh trắc học) bằng cách phân tích ảnh hoặc video selfie.",
            "features": [
                "Phát hiện giả mạo qua màn hình điện thoại, ảnh in giấy hoặc mặt nạ silicon",
                "Hỗ trợ cả cơ chế Active Liveness và Passive Liveness",
                "Đạt tiêu chuẩn bảo mật ngân hàng"
            ]
        },
        "document": {
            "endpoint_url": "http://localhost:8000/v1/vision/liveness-v3",
            "method": "POST",
            "content_type": "multipart/form-data",
            "headers": [
                {"name": "Authorization", "type": "string", "required": True, "desc": "Bearer <YOUR_API_KEY>"}
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
        "id": "fa0d3bec-46a9-41ba-2d6b-39725ae98123",
        "api_id": "api_summarization",
        "endpoint_id": "/v1/nlp/summarization",
        "path": "/v1/nlp/summarization",
        "method": "POST",
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
                "Dựa trên mô hình ngôn ngữ chuyên sâu tiếng Việt"
            ]
        },
        "document": {
            "endpoint_url": "http://localhost:8000/v1/nlp/summarization",
            "method": "POST",
            "content_type": "application/json",
            "headers": [
                {"name": "Authorization", "type": "string", "required": True, "desc": "Bearer <YOUR_API_KEY>"},
                {"name": "Content-Type", "type": "string", "required": True, "desc": "application/json"}
            ],
            "parameters": [
                {"name": "document", "type": "string", "required": True, "desc": "Nội dung văn bản dài cần tóm tắt"},
                {"name": "ratio", "type": "number", "required": False, "desc": "Tỷ lệ tóm tắt (mặc định: 0.2)"}
            ],
            "sample_response": '{\n  "status": "success",\n  "summary": "AIP Platform ra mắt bộ 13 API dịch vụ trí tuệ nhân tạo thế hệ mới..."\n}'
        },
        "pricing": {
            "free_quota": "10,000 requests miễn phí",
            "pay_as_you_go": "50 VNĐ / request",
            "billing_cycle": "Thanh toán theo lượt tóm tắt"
        }
    }
]


class MongoEndpointRepository(IEndpointRepository):
    """MongoDB Atlas implementation for Endpoints serving as full API Catalog with FPT.AI ID compliance."""

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
                default_id_map = {e["endpoint_id"]: e.get("id") for e in DEFAULT_ENDPOINTS}
                api_id_map = {e.get("api_id"): e.get("id") for e in DEFAULT_ENDPOINTS if e.get("api_id")}

                # 1. Start with complete defaults
                for e in DEFAULT_ENDPOINTS:
                    self._endpoints_cache[e["endpoint_id"]] = dict(e)

                # 2. Overlay existing DB items
                for item in eps:
                    item.pop("_id", None)
                    ep_id = item.get("endpoint_id")
                    if not item.get("id"):
                        item["id"] = default_id_map.get(ep_id) or api_id_map.get(item.get("api_id"))
                    self._endpoints_cache[ep_id] = item

                # 3. Insert any missing default endpoints to MongoDB
                existing_ep_ids = {item.get("endpoint_id") for item in eps}
                missing_eps = [dict(e) for e in DEFAULT_ENDPOINTS if e.get("endpoint_id") not in existing_ep_ids]
                if missing_eps:
                    try:
                        await db.endpoints.insert_many(missing_eps)
                    except Exception:
                        pass

                return self._endpoints_cache
            except Exception:
                pass

        # Fallback to defaults if DB completely fails
        if not self._endpoints_cache:
            self._endpoints_cache = {e["endpoint_id"]: dict(e) for e in DEFAULT_ENDPOINTS}
        return self._endpoints_cache

    async def get_endpoint_by_id(self, identifier: str) -> Optional[Dict[str, Any]]:
        """Find an endpoint by UUID id, api_id, or endpoint_id."""
        endpoints = await self.list_endpoints()
        for ep in endpoints.values():
            if ep.get("id") == identifier or ep.get("api_id") == identifier or ep.get("endpoint_id") == identifier:
                return ep
        return None

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
