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
from common.repositories.endpoint_repository import endpoint_repository
from common.repositories.api_subscription_repository import api_subscription_repository
from common.repositories.api_log_repository import AI_API_LOG_PATHS
from common.security.argon2_hasher import generate_api_key

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


class RechargeBalanceRequest(BaseModel):
    credits: int
    amount: str
    package: str
    project: Optional[str] = "default"


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
    keys = await key_repository.list_keys()
    if not keys:
        default_key = {
            "key_id": f"key_{secrets.token_hex(6)}",
            "name": "hello",
            "value": "SSAmMKZJHIgM82n0NTnFQq6Q3CkIjLR",
            "project_name": "wwrwer23",
            "created_at": datetime.now(timezone.utc).strftime("%Y/%m/%d %H:%M"),
        }
        await key_repository.create_key(default_key)
        return [default_key]
    return keys


@router.post("/api-keys", status_code=status.HTTP_201_CREATED)
async def create_user_api_key(req: ApiKeyCreateRequest):
    """Generate and store a new API Key in MongoDB Atlas."""
    raw_key, hashed_key = generate_api_key(prefix="aip_live_")
    key_doc = {
        "key_id": f"key_{secrets.token_hex(6)}",
        "name": req.name,
        "prefix": raw_key[:12] + "...",
        "hashed_key": hashed_key,
        "project_name": req.project_name or "Default Project",
        "created_at": datetime.now(timezone.utc).strftime("%Y/%m/%d %H:%M"),
    }
    saved = await key_repository.create_key(key_doc)
    return {
        "message": f"API Key '{req.name}' created successfully!",
        "api_key": raw_key,
        "key": {key: value for key, value in saved.items() if key != "hashed_key"},
    }


@router.delete("/api-keys/{key_id}")
async def delete_user_api_key(key_id: str):
    """Revoke an API key in MongoDB Atlas."""
    success = await key_repository.delete_key(key_id)
    return {"message": "API key revoked successfully", "success": success}


# --- 3. PAYMENTS & TRANSACTIONS REST ENDPOINTS ---
@router.get("/payments", response_model=List[dict])
async def list_user_payments():
    """Fetch payment history transactions directly from MongoDB Atlas payments collection."""
    from common.database.mongodb import mongo_manager
    db = mongo_manager.get_database()
    if db is not None:
        try:
            cursor = db.payments.find({"user_id": "user_staff_01"}, {"_id": 0}).sort("_id", -1)
            docs = await cursor.to_list(100)
            if docs:
                return docs
        except Exception:
            pass
    return []


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
    """Get active API states for user from MongoDB Atlas api_subscriptions collection."""
    enabled = await api_subscription_repository.get_user_subscriptions("user_staff_01")
    return {"enabled_apis": enabled}


@router.post("/apis-state")
async def update_user_apis_state(req: ApisStateUpdateRequest):
    """Update active API states for user in MongoDB Atlas api_subscriptions collection."""
    updated = await api_subscription_repository.update_user_subscriptions("user_staff_01", req.enabled_apis)
    return {"message": "API states updated successfully", "enabled_apis": updated}


# --- 5. SUBSCRIPTION BALANCE & RECHARGE REST ENDPOINTS ---
@router.get("/balance")
async def get_user_balance():
    """Get paid balance from MongoDB Atlas api_subscriptions collection."""
    bal = await api_subscription_repository.get_user_paid_balance("user_staff_01")
    return {"paid_balance": bal}


@router.post("/recharge")
async def recharge_user_balance(req: RechargeBalanceRequest):
    """Recharge credits and record payment in MongoDB Atlas."""
    new_bal = await api_subscription_repository.recharge_user_balance(
        user_id="user_staff_01",
        add_credits=req.credits,
        amount=req.amount,
        package=req.package,
        project=req.project or "default"
    )
    return {"message": "Recharged successfully", "paid_balance": new_bal}


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

@router.get("/apis-catalog", response_model=List[dict])
async def list_database_apis_catalog():
    """Fetch all available API services catalog from MongoDB Atlas endpoints."""
    endpoints_map = await endpoint_repository.list_endpoints()
    return list(endpoints_map.values())


# --- 7. API USAGE REPORT LOGS FOR STAFF REPORT PAGE ---

@router.get("/api-report", summary="List API Call Logs with Filtering (Staff Report)")
async def list_api_report_logs(
    status: Optional[str] = None,
    api: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    page: int = 1,
    page_size: int = 25,
):
    """
    Fetch API call execution logs from MongoDB with optional filters.
    Used by the Staff API Report page.

    - **status**: Filter by HTTP status code group: "200", "400", "500"
    - **api**: Filter by API path keyword (e.g. "speech", "completions")
    - **from_date**: Start date (YYYY/MM/DD or YYYY-MM-DD)
    - **to_date**: End date (YYYY/MM/DD or YYYY-MM-DD)
    - **page**: Page number (default 1)
    - **page_size**: Items per page (default 25)
    """
    from common.database.mongodb import mongo_manager

    db = mongo_manager.get_database()
    if db is None:
        # Fallback to in-memory cache if no DB
        from common.repositories.api_log_repository import api_log_repository
        logs = await api_log_repository.list_recent_logs(limit=500)
        # Apply client-side filtering on cache
        filtered = _filter_logs(logs, status, api, from_date, to_date)
        total = len(filtered)
        start = (page - 1) * page_size
        return {
            "object": "list",
            "data": filtered[start:start + page_size],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    # Build MongoDB query
    # Keep historical control-plane records out of the report as well.
    query: Dict = {"path": {"$in": AI_API_LOG_PATHS}}

    if status:
        if status == "200":
            query["status_code"] = {"$gte": 200, "$lt": 300}
        elif status == "400":
            query["status_code"] = {"$gte": 400, "$lt": 500}
        elif status == "500":
            query["status_code"] = {"$gte": 500, "$lt": 600}

    if api:
        # Map friendly name to path substring
        api_path_map = {
            "Speech to Text": "/v1/audio/transcriptions",
            "Text to Speech": "/v1/audio/speech",
            "LLM Chatbot": "/v1/chat/completions",
            "Embeddings": "/v1/embeddings",
            "Image Generation": "/v1/images",
            "Moderation": "/v1/moderations",
            "OCR": "/v1/ocr",
            "Translation": "/v1/translations",
        }
        path_fragment = api_path_map.get(api, api.lower())
        query["path"] = {"$regex": path_fragment, "$options": "i"}

    if from_date or to_date:
        ts_filter = {}
        if from_date:
            clean = from_date.replace("/", "-")
            ts_filter["$gte"] = f"{clean}T00:00:00+00:00"
        if to_date:
            clean = to_date.replace("/", "-")
            ts_filter["$lte"] = f"{clean}T23:59:59+00:00"
        if ts_filter:
            query["timestamp"] = ts_filter

    try:
        total = await db.api_logs.count_documents(query)
        skip = (page - 1) * page_size
        cursor = db.api_logs.find(query, {"_id": 0}).sort("timestamp", -1).skip(skip).limit(page_size)
        logs = await cursor.to_list(length=page_size)
    except Exception:
        logs = []
        total = 0

    return {
        "object": "list",
        "data": logs,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def _filter_logs(logs: list, status: str = None, api: str = None, from_date: str = None, to_date: str = None) -> list:
    """Client-side filtering fallback when MongoDB is unavailable."""
    result = logs
    if status:
        if status == "200":
            result = [l for l in result if 200 <= l.get("status_code", 0) < 300]
        elif status == "400":
            result = [l for l in result if 400 <= l.get("status_code", 0) < 500]
        elif status == "500":
            result = [l for l in result if 500 <= l.get("status_code", 0) < 600]
    if api:
        api_lower = api.lower()
        result = [l for l in result if api_lower in l.get("path", "").lower()]
    if from_date:
        clean = from_date.replace("/", "-")
        result = [l for l in result if l.get("timestamp", "") >= f"{clean}T00:00:00"]
    if to_date:
        clean = to_date.replace("/", "-")
        result = [l for l in result if l.get("timestamp", "") <= f"{clean}T23:59:59"]
    return result

