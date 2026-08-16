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
    """Get active API states for user from MongoDB Atlas api_subscriptions collection."""
    enabled = await api_subscription_repository.get_user_subscriptions("user_staff_01")
    return {"enabled_apis": enabled}


@router.post("/apis-state")
async def update_user_apis_state(req: ApisStateUpdateRequest):
    """Update active API states for user in MongoDB Atlas api_subscriptions collection."""
    updated = await api_subscription_repository.update_user_subscriptions("user_staff_01", req.enabled_apis)
    return {"message": "API states updated successfully", "enabled_apis": updated}


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
