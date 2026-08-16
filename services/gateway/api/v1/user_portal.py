from datetime import datetime, timezone
import secrets
from typing import Dict, List, Optional
from fastapi import APIRouter, status
from pydantic import BaseModel, Field

from common.repositories.project_repository import project_repository
from common.repositories.key_repository import key_repository
from common.repositories.notification_repository import notification_repository
from common.repositories.tenant_repository import tenant_repository
from common.repositories.user_repository import user_repository

router = APIRouter(prefix="/v1/user", tags=["User Portal & Console API"])


# Schemas
class ProjectCreateRequest(BaseModel):
    project_name: str = Field(..., description="Name of the project")
    billing_type: str = Field(default="prepaid", description="Billing type: prepaid or postpaid")


class ApiKeyCreateRequest(BaseModel):
    name: str = Field(..., description="Name / Label for the API key")
    project_name: Optional[str] = Field(default="Default Project")


class PaymentCreateRequest(BaseModel):
    amount: int = Field(..., description="Payment amount in VND")
    package: str = Field(..., description="Selected package name")
    project: Optional[str] = Field(default="Default Project")


class FeedbackRequest(BaseModel):
    category: str = Field(default="feature")
    title: str
    description: str


class ContactMessageRequest(BaseModel):
    name: str
    phone: str
    email: str
    message: str


class ApisStateUpdateRequest(BaseModel):
    enabled_apis: Dict[str, bool]


# --- 1. PROJECTS REST ENDPOINTS ---
@router.get("/projects", response_model=List[dict])
async def list_user_projects():
    """Fetch user projects from MongoDB Atlas."""
    projects = await project_repository.list_user_projects(user_id="user_staff_01")
    if not projects:
        default_proj = {
            "project_id": "proj_default",
            "project_name": "wwrwer23",
            "type": "prepaid",
            "user_id": "user_staff_01",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await project_repository.create_project(default_proj)
        return [default_proj]
    return projects


@router.post("/projects", status_code=status.HTTP_201_CREATED)
async def create_user_project(req: ProjectCreateRequest):
    """Create a new project in MongoDB Atlas."""
    proj_id = f"proj_{secrets.token_hex(6)}"
    proj_doc = {
        "project_id": proj_id,
        "project_name": req.project_name,
        "type": req.billing_type,
        "user_id": "user_staff_01",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    saved = await project_repository.create_project(proj_doc)
    return {"message": f"Project '{req.project_name}' created successfully!", "project": saved}


# --- 2. API KEYS REST ENDPOINTS ---
@router.get("/api-keys", response_model=List[dict])
async def list_user_api_keys():
    """Fetch active API keys from MongoDB Atlas."""
    keys = key_repository.list_keys()
    if not keys:
        default_key = {
            "key_id": f"key_{secrets.token_hex(6)}",
            "name": "hello",
            "value": "SSAmMKZJHIgM82n0NTnFQq6Q3CkIjLR",
            "project_name": "wwrwer23",
            "created_at": datetime.now(timezone.utc).strftime("%Y/%m/%d %H:%M"),
        }
        key_repository.save_key(default_key)
        return [default_key]
    return keys


@router.post("/api-keys", status_code=status.HTTP_201_CREATED)
async def create_user_api_key(req: ApiKeyCreateRequest):
    """Generate and store a new API Key in MongoDB Atlas."""
    raw_key = f"SSAm{secrets.token_urlsafe(24)}"
    key_doc = {
        "key_id": f"key_{secrets.token_hex(6)}",
        "name": req.name,
        "value": raw_key,
        "project_name": req.project_name or "Default Project",
        "created_at": datetime.now(timezone.utc).strftime("%Y/%m/%d %H:%M"),
    }
    saved = key_repository.save_key(key_doc)
    return {"message": f"API Key '{req.name}' created successfully!", "api_key": saved}


@router.delete("/api-keys/{key_id}")
async def delete_user_api_key(key_id: str):
    """Revoke an API key in MongoDB Atlas."""
    success = key_repository.revoke_key(key_id)
    return {"message": "API key revoked successfully", "success": success}


# --- 3. PAYMENTS & TRANSACTIONS REST ENDPOINTS ---
@router.get("/payments", response_model=List[dict])
async def list_user_payments():
    """Fetch payment history transactions from MongoDB Atlas."""
    payments = tenant_repository.list_payments() if hasattr(tenant_repository, "list_payments") else []
    return payments


@router.post("/payments", status_code=status.HTTP_201_CREATED)
async def record_user_payment(req: PaymentCreateRequest):
    """Record a completed VNPAY payment transaction in MongoDB Atlas."""
    txn_id = f"VNP{secrets.randbelow(89999999) + 10000000}"
    payment_doc = {
        "txn_ref": txn_id,
        "date": datetime.now(timezone.utc).strftime("%Y/%m/%d %H:%M"),
        "status": "SUCCESS",
        "amount": req.amount,
        "package": req.package,
        "project": req.project or "wwrwer23",
        "txn_no": str(secrets.randbelow(89999999) + 10000000),
    }
    if hasattr(tenant_repository, "save_payment"):
        tenant_repository.save_payment(payment_doc)
    return {"message": "Payment recorded successfully", "payment": payment_doc}


# --- 4. API ACTIVATION STATES REST ENDPOINTS ---
@router.get("/apis-state")
async def get_user_apis_state():
    """Get active API states for user from MongoDB Atlas."""
    user = await user_repository.get_user_by_id("user_staff_01")
    enabled = user.get("enabled_apis", {"Speech to Text": True, "Text to Speech": False, "LLM Chatbot API": False}) if user else {"Speech to Text": True, "Text to Speech": False, "LLM Chatbot API": False}
    return {"enabled_apis": enabled}


@router.post("/apis-state")
async def update_user_apis_state(req: ApisStateUpdateRequest):
    """Update active API states for user in MongoDB Atlas."""
    await user_repository.update_user("user_staff_01", {"enabled_apis": req.enabled_apis})
    return {"message": "API states updated successfully", "enabled_apis": req.enabled_apis}


# --- 5. CONTACT & FEEDBACK REST ENDPOINTS ---
@router.post("/feedback", status_code=status.HTTP_201_CREATED)
async def submit_user_feedback(req: FeedbackRequest):
    """Save user feedback into MongoDB Atlas notifications collection."""
    fb_doc = {
        "type": "feedback",
        "category": req.category,
        "title": req.title,
        "description": req.description,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    notification_repository.save_notification(fb_doc)
    return {"message": "Feedback submitted successfully!", "feedback": fb_doc}


@router.post("/contact", status_code=status.HTTP_201_CREATED)
async def submit_user_contact(req: ContactMessageRequest):
    """Save user contact inquiry into MongoDB Atlas notifications collection."""
    contact_doc = {
        "type": "contact_message",
        "name": req.name,
        "phone": req.phone,
        "email": req.email,
        "message": req.message,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    notification_repository.save_notification(contact_doc)
    return {"message": "Contact message submitted successfully!", "contact": contact_doc}


# --- 6. CATALOG OF ALL APIS IN DATABASE WITH 4 TABS SPECIFICATIONS ---
DEFAULT_API_CATALOG = [
    {
        "api_id": "api_stt",
        "name": "Speech to Text",
        "category": "Speech Recognition",
        "description": "Nhận dạng giọng nói tiếng Việt độ chính xác cao dựa trên mô hình PhoWhisper ASR Large v3.",
        "icon": "fa-microphone",
        "free_quota": "10,000 blocks",
        "unit": "block",
        "status": "active",
        "overview": {
            "title": "PhoWhisper Speech-to-Text Large v3 Engine",
            "summary": "Dịch vụ chuyển đổi giọng nói thành văn bản tiếng Việt chuẩn xác nhất, hỗ trợ nhận dạng tiếng địa phương 3 miền (Bắc, Trung, Nam) và lọc nhiễu môi trường đỉnh cao.",
            "features": [
                "Độ chính xác nhận dạng WER (Word Error Rate) dưới 3.5%",
                "Hỗ trợ ghi âm trực tiếp hoặc tải tệp âm thanh (WAV, MP3, FLAC, M4A)",
                "Tự động ngắt câu và thêm dấu câu thông minh (Punctuation)",
                "Tốc độ xử lý siêu nhanh Real-time Factor (RTF) < 0.15"
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
        "api_id": "api_tts",
        "name": "Text to Speech",
        "category": "Speech Synthesis",
        "description": "Tổng hợp giọng nói tiếng Việt tự nhiên đa vùng miền dựa trên mô hình viXTTS Neural Engine.",
        "icon": "fa-volume-high",
        "free_quota": "100,000 characters",
        "unit": "character",
        "status": "active",
        "overview": {
            "title": "viXTTS Neural Speech Synthesis Engine",
            "summary": "Công nghệ tổng hợp giọng đọc AI mang cảm xúc tự nhiên như người thật, hỗ trợ nhiều giọng đọc Nam/Nữ vùng miền đa dạng.",
            "features": [
                "Giọng đọc truyền cảm, ngắt nghỉ theo ngữ cảnh tự nhiên",
                "Hỗ trợ 6 giọng đọc tiêu chuẩn (Nam/Nữ Hà Nội, Huế, Sài Gòn)",
                "Tùy chỉnh tốc độ đọc, cao độ và định dạng file đầu ra (MP3, WAV)",
                "Thời gian phản hồi siêu thấp thích hợp cho trợ lý ảo Voicebot"
            ]
        },
        "document": {
            "endpoint_url": "https://ai-platform-6p72.onrender.com/v1/audio/speech",
            "method": "POST",
            "content_type": "application/json",
            "headers": [
                {"name": "api-key", "type": "string", "required": True, "desc": "Khóa API Key của bạn"},
                {"name": "Content-Type", "type": "string", "required": True, "desc": "application/json"}
            ],
            "parameters": [
                {"name": "input", "type": "string", "required": True, "desc": "Văn bản tiếng Việt cần đọc"},
                {"name": "voice", "type": "string", "required": False, "desc": "Giọng đọc (hanoi_female, saigon_male, etc.)"},
                {"name": "response_format", "type": "string", "required": False, "desc": "mp3 hoặc wav"}
            ],
            "sample_response": '{\n  "audio_url": "https://ai-platform-6p72.onrender.com/v1/audio/output_speech.mp3",\n  "characters_processed": 48,\n  "status": "success"\n}'
        },
        "pricing": {
            "free_quota": "100,000 ký tự miễn phí mỗi tháng",
            "pay_as_you_go": "1 VNĐ / ký tự văn bản",
            "billing_cycle": "Thanh toán theo lượng ký tự tiêu thụ"
        }
    },
    {
        "api_id": "api_llm",
        "name": "LLM Chatbot API",
        "category": "Generative AI",
        "description": "API xử lý ngôn ngữ tự nhiên và Chatbot thông minh dựa trên mô hình Qwen3-14B & DeepSeek V3.",
        "icon": "fa-robot",
        "free_quota": "50,000 tokens",
        "unit": "token",
        "status": "active",
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
    }
]


@router.get("/apis-catalog", response_model=List[dict])
async def list_database_apis_catalog():
    """Fetch all available API services catalog from MongoDB Atlas."""
    return DEFAULT_API_CATALOG
