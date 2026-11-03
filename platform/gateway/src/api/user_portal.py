import uuid
import secrets
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional
from fastapi import APIRouter, status, Request, Query
from pydantic import BaseModel, Field

from common.repositories.project_repository import project_repository
from common.repositories.key_repository import key_repository
from common.repositories.notification_repository import notification_repository
from common.repositories.tenant_repository import tenant_repository
from common.repositories.endpoint_repository import endpoint_repository
from common.repositories.api_subscription_repository import api_subscription_repository
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


DEFAULT_PROJECT_ID = "f40b6a70-ea64-4d01-90dc-53a2d7a81395"


def get_current_user_id(request: Request) -> str:
    user_id = request.headers.get("x-user-id") or request.headers.get("X-User-Id")
    if user_id:
        return user_id
    auth = request.headers.get("authorization") or request.headers.get("Authorization", "")
    if auth.startswith("Bearer aip_session_"):
        return auth.replace("Bearer aip_session_", "").strip()
    return "user_staff_01"


# --- 1. PROJECTS REST ENDPOINTS ---
@router.get("/projects", response_model=List[dict])
async def list_user_projects(request: Request):
    """Fetch user projects from MongoDB Atlas."""
    user_id = get_current_user_id(request)
    projects = await project_repository.list_user_projects(user_id=user_id)
    if not projects:
        default_proj = {
            "project_id": str(uuid.uuid4()) if user_id != "user_staff_01" else DEFAULT_PROJECT_ID,
            "project_name": "Default Project",
            "type": "prepaid",
            "user_id": user_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await project_repository.create_project(default_proj)
        return [default_proj]
    return projects


@router.post("/projects", status_code=status.HTTP_201_CREATED)
async def create_user_project(req: ProjectCreateRequest, request: Request):
    """Create a new project in MongoDB Atlas."""
    user_id = get_current_user_id(request)
    proj_id = str(uuid.uuid4())
    proj_doc = {
        "project_id": proj_id,
        "project_name": req.project_name,
        "type": req.billing_type,
        "user_id": user_id,
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
        raw_key, hashed_key = generate_api_key(prefix="aip_live_")
        default_key = {
            "key_id": f"key_{secrets.token_hex(6)}",
            "name": "Default Key",
            "value": raw_key,
            "prefix": raw_key[:12] + "...",
            "hashed_key": hashed_key,
            "project_name": "Default Project",
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
        "tenant_id": "TENANT_RETAIL_BANK",
        "status": "enabled",
        "rpm_limit": 120,
        "tpm_limit": 200000,
        "concurrency_limit": 10,
        "allowed_aliases": ["*"],
        "allowed_endpoints": ["*"],
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
async def list_user_payments(request: Request):
    """Fetch payment history transactions directly from MongoDB Atlas payments collection."""
    from common.database.mongodb import mongo_manager
    db = mongo_manager.get_database()
    user_id = get_current_user_id(request)
    if db is not None:
        try:
            cursor = db.payments.find({"user_id": user_id}, {"_id": 0}).sort("_id", -1)
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
        "project": req.project or "Default Project",
        "txn_no": str(secrets.randbelow(89999999) + 10000000),
    }
    if hasattr(tenant_repository, "save_payment"):
        tenant_repository.save_payment(payment_doc)
    return {"message": "Payment recorded successfully", "payment": payment_doc}


# --- 4. API ACTIVATION STATES REST ENDPOINTS ---
@router.get("/apis-state")
@router.get("/apis")
async def get_user_apis_state(request: Request):
    """Get active API states for user from MongoDB Atlas api_subscriptions collection."""
    user_id = get_current_user_id(request)
    enabled = await api_subscription_repository.get_user_subscriptions(user_id)
    return {"enabled_apis": enabled}


@router.post("/apis-state")
@router.post("/apis")
async def update_user_apis_state(req: ApisStateUpdateRequest, request: Request):
    """Update active API states for user in MongoDB Atlas api_subscriptions collection."""
    user_id = get_current_user_id(request)
    updated = await api_subscription_repository.update_user_subscriptions(user_id, req.enabled_apis)
    return {"message": "API states updated successfully", "enabled_apis": updated}


# --- 5. SUBSCRIPTION BALANCE & RECHARGE REST ENDPOINTS ---
@router.get("/balance")
async def get_user_balance(request: Request):
    """Get paid balance from MongoDB Atlas api_subscriptions collection."""
    user_id = get_current_user_id(request)
    bal = await api_subscription_repository.get_user_paid_balance(user_id)
    return {"paid_balance": bal}


@router.post("/recharge")
async def recharge_user_balance(req: RechargeBalanceRequest, request: Request):
    """Recharge credits and record payment in MongoDB Atlas."""
    user_id = get_current_user_id(request)
    new_bal = await api_subscription_repository.recharge_user_balance(
        user_id=user_id,
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

@router.get("/catalog", response_model=List[dict])
@router.get("/apis-catalog", response_model=List[dict])
async def list_database_apis_catalog():
    """Fetch all available API services catalog from MongoDB Atlas endpoints."""
    endpoints_map = await endpoint_repository.list_endpoints()
    return list(endpoints_map.values())


# --- 7. GPU HARDWARE & VRAM UTILIZATION TELEMETRY ---
@router.get("/gpu-status")
async def get_user_gpu_status():
    """Get GPU VRAM and node resource utilization status for staff portal."""
    from src.resources.telemetry import get_gpu_telemetry

    telemetry = get_gpu_telemetry()
    total = telemetry.get("vram_total_mb", 4096.0)
    used = telemetry.get("vram_used_mb", 0.0)

    # Calculate allocated VRAM based on active API subscriptions
    try:
        enabled_apis = await api_subscription_repository.get_user_subscriptions("user_staff_01")
        active_count = sum(1 for v in enabled_apis.values() if v)
    except Exception:
        active_count = 1

    # Base memory: 1200 MB + 260 MB per enabled AI service
    estimated_used = 1200.0 + (active_count * 260.0)
    final_used = min(total, max(used, estimated_used))
    pct = round((final_used / total) * 100, 1) if total > 0 else 0
    temp = telemetry.get("temperature_celsius", 56.0)

    return {
        "gpu_detected": True,
        "name": telemetry.get("gpu_name", "NVIDIA GeForce RTX 3050 Laptop GPU"),
        "vram_total_mb": total,
        "vram_used_mb": round(final_used, 1),
        "vram_free_mb": round(max(0.0, total - final_used), 1),
        "vram_percentage": pct,
        "temperature_c": temp,
        "active_services_count": active_count,
        "threshold_warning": pct >= 80.0,
        "status": telemetry.get("status", "online"),
    }


@router.get("/api-summary", summary="Get API usage counts and token breakdown from MongoDB")
async def get_user_api_usage_summary(request: Request):
    """Aggregate request, error, and token counts for API endpoints in the database catalog."""
    from common.database.mongodb import mongo_manager
    from common.repositories.api_subscription_repository import api_subscription_repository

    db = mongo_manager.get_database()
    if db is None:
        raise RuntimeError("MongoDB is unavailable; API usage summary cannot be loaded")

    endpoints = await endpoint_repository.list_endpoints()
    endpoint_map = {}
    for ep in endpoints.values():
        p = ep.get("path") or ep.get("endpoint_id")
        if p:
            endpoint_map[p] = ep

    paths = list(endpoint_map.keys())
    if not paths:
        return {
            "data": [],
            "total_requests": 0,
            "total_errors": 0,
            "total_tokens_used": 0,
            "paid_balance": 50000,
            "monthly_limit": 100000,
            "tier": "Enterprise Developer",
            "rpm_limit": 1200,
            "concurrency_limit": 50,
        }

    pipeline = [
        {"$match": {"path": {"$in": paths}}},
        {
            "$group": {
                "_id": "$path",
                "requests": {"$sum": 1},
                "errors": {
                    "$sum": {
                        "$cond": [
                            {"$gte": [{"$ifNull": ["$status_code", 0]}, 400]},
                            1,
                            0,
                        ]
                    }
                },
            }
        },
    ]
    cursor = db.api_logs.aggregate(pipeline)
    counts = await cursor.to_list(length=None)
    counts_map = {item["_id"]: item for item in counts}

    def get_token_rate(path: str) -> int:
        if "/chat" in path or "/completions" in path or "/rag" in path:
            return 15
        elif "/audio" in path or "/speech" in path or "/transcriptions" in path:
            return 10
        elif "/images" in path:
            return 20
        elif "/vision" in path or "/ocr" in path:
            return 5
        elif "/embeddings" in path or "/nlp" in path:
            return 2
        return 1

    user_id = get_current_user_id(request)
    paid_balance = await api_subscription_repository.get_user_paid_balance(user_id)

    total_requests = 0
    total_errors = 0
    total_tokens_used = 0
    data = []

    for path, ep in endpoint_map.items():
        cnt = counts_map.get(path, {"requests": 0, "errors": 0})
        reqs = cnt.get("requests", 0)
        errs = cnt.get("errors", 0)
        rate = get_token_rate(path)
        tokens = reqs * rate

        fq_raw = ep.get("free_quota", "50000")
        try:
            fq_num = int("".join(c for c in str(fq_raw).split()[0] if c.isdigit()))
        except Exception:
            fq_num = 50000

        free_remain = max(0, fq_num - reqs)

        total_requests += reqs
        total_errors += errs
        total_tokens_used += tokens

        data.append({
            "path": path,
            "name": ep.get("name") or path,
            "category": ep.get("category") or "AI Service",
            "token_rate": rate,
            "requests": reqs,
            "errors": errs,
            "tokens_used": tokens,
            "free_quota": fq_num,
            "free_remain": free_remain,
            "status": "Active" if free_remain > 0 else "Exceeded",
        })

    data.sort(key=lambda x: x["requests"], reverse=True)

    return {
        "data": data,
        "total_requests": total_requests,
        "total_errors": total_errors,
        "total_tokens_used": total_tokens_used,
        "paid_balance": paid_balance,
        "monthly_limit": 100000,
        "tier": "Enterprise Developer",
        "rpm_limit": 1200,
        "concurrency_limit": 50,
    }


# --- 7B. REAL-TIME TELEMETRY TIME-SERIES FOR CONSOLE DASHBOARD ---

@router.get("/analytics/timeseries", summary="Get telemetry time-series for Traffic, Errors, and Latency")
@router.get("/analytics-timeseries", summary="Alias for telemetry time-series")
async def get_analytics_timeseries(
    request: Request,
    range: str = Query("last 1 day", description="Quick range name (e.g. today, last 1 day, last 7 days)"),
    interval: Optional[str] = Query(None, description="Interval step (e.g. 1 hour, 1 day, 1 minute)"),
    mode: str = Query("quick", description="Filter mode: quick | absolute | interval"),
    from_date: Optional[str] = Query(None, description="Start date for absolute mode (YYYY-MM-DD)"),
    to_date: Optional[str] = Query(None, description="End date for absolute mode (YYYY-MM-DD)"),
):
    """
    Returns real-time telemetry time-series points aggregated from MongoDB api_logs.
    Powers the Traffic, Errors, and Median Latency charts on the Console Dashboard.
    """
    from common.database.mongodb import mongo_manager

    # Normalize parameters if invoked directly outside FastAPI request pipeline
    r_val = range if isinstance(range, str) else "last 1 day"
    iv_val = interval if isinstance(interval, str) else None
    mode_val = mode if isinstance(mode, str) else "quick"
    from_val = from_date if isinstance(from_date, str) else None
    to_val = to_date if isinstance(to_date, str) else None

    db = mongo_manager.get_database()
    now_utc = datetime.now(timezone.utc)
    vn_tz = timezone(timedelta(hours=7))
    now_vn = now_utc.astimezone(vn_tz)

    if mode_val == "absolute" and from_val and to_val:
        try:
            start_dt = datetime.strptime(from_val.strip()[:10], "%Y-%m-%d").replace(tzinfo=vn_tz).astimezone(timezone.utc)
        except Exception:
            start_dt = now_utc - timedelta(days=1)
        try:
            end_dt = datetime.strptime(to_val.strip()[:10], "%Y-%m-%d").replace(hour=23, minute=59, second=59, tzinfo=vn_tz).astimezone(timezone.utc)
        except Exception:
            end_dt = now_utc
    else:
        r = (r_val or "last 1 day").lower().strip()
        if r == "today":
            start_dt = now_vn.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)
            end_dt = now_utc
        elif r == "this week":
            start_dt = (now_vn - timedelta(days=now_vn.weekday())).replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)
            end_dt = now_utc
        elif r == "this month":
            start_dt = now_vn.replace(day=1, hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)
            end_dt = now_utc
        elif r == "this year":
            start_dt = now_vn.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)
            end_dt = now_utc
        elif r == "last 5 minutes":
            start_dt = now_utc - timedelta(minutes=5)
            end_dt = now_utc
        elif r == "last 15 minutes":
            start_dt = now_utc - timedelta(minutes=15)
            end_dt = now_utc
        elif r == "last 30 minutes":
            start_dt = now_utc - timedelta(minutes=30)
            end_dt = now_utc
        elif r == "last 45 minutes":
            start_dt = now_utc - timedelta(minutes=45)
            end_dt = now_utc
        elif r == "last 1 hour":
            start_dt = now_utc - timedelta(hours=1)
            end_dt = now_utc
        elif r == "last 2 hours":
            start_dt = now_utc - timedelta(hours=2)
            end_dt = now_utc
        elif r == "last 6 hours":
            start_dt = now_utc - timedelta(hours=6)
            end_dt = now_utc
        elif r == "last 12 hours":
            start_dt = now_utc - timedelta(hours=12)
            end_dt = now_utc
        elif r in ("last 1 day", "last 24 hours"):
            start_dt = now_utc - timedelta(hours=24)
            end_dt = now_utc
        elif r == "last 3 days":
            start_dt = now_utc - timedelta(days=3)
            end_dt = now_utc
        elif r == "last 7 days":
            start_dt = now_utc - timedelta(days=7)
            end_dt = now_utc
        elif r == "last 14 days":
            start_dt = now_utc - timedelta(days=14)
            end_dt = now_utc
        elif r in ("last 1 month", "last 30 days"):
            start_dt = now_utc - timedelta(days=30)
            end_dt = now_utc
        elif r == "last 3 months":
            start_dt = now_utc - timedelta(days=90)
            end_dt = now_utc
        elif r == "last 6 months":
            start_dt = now_utc - timedelta(days=180)
            end_dt = now_utc
        elif r in ("last 12 months", "last 1 year"):
            start_dt = now_utc - timedelta(days=365)
            end_dt = now_utc
        else:
            start_dt = now_utc - timedelta(hours=24)
            end_dt = now_utc

    duration_sec = max(1.0, (end_dt - start_dt).total_seconds())

    iv = (iv_val or "").lower().strip()
    if "min" in iv:
        unit = "minute"
        step_sec = 60
        fmt = "%H:%M"
    elif "hour" in iv:
        unit = "hour"
        step_sec = 3600
        fmt = "%H:00"
    elif "day" in iv:
        unit = "day"
        step_sec = 86400
        fmt = "%d/%m"
    elif "week" in iv:
        unit = "week"
        step_sec = 86400 * 7
        fmt = "%d/%m"
    elif "month" in iv:
        unit = "month"
        step_sec = 86400 * 30
        fmt = "%m/%Y"
    elif "year" in iv:
        unit = "year"
        step_sec = 86400 * 365
        fmt = "%Y"
    else:
        if duration_sec <= 3600:
            unit = "minute"
            step_sec = 60
            fmt = "%H:%M"
        elif duration_sec <= 86400 * 2:
            unit = "hour"
            step_sec = 3600
            fmt = "%H:00"
        elif duration_sec <= 86400 * 45:
            unit = "day"
            step_sec = 86400
            fmt = "%d/%m"
        elif duration_sec <= 86400 * 180:
            unit = "week"
            step_sec = 86400 * 7
            fmt = "%d/%m"
        else:
            unit = "month"
            step_sec = 86400 * 30
            fmt = "%m/%Y"

    data_map = {}
    if db is not None:
        try:
            start_iso = start_dt.isoformat()
            end_iso = end_dt.isoformat()

            pipeline = [
                {"$match": {
                    "timestamp": {"$gte": start_iso, "$lte": end_iso}
                }},
                {"$project": {
                    "bucket": {
                        "$dateTrunc": {
                            "date": {"$toDate": "$timestamp"},
                            "unit": unit
                        }
                    },
                    "status_code": {"$ifNull": ["$status_code", 200]},
                    "latency_ms": {"$ifNull": ["$latency_ms", 0.0]}
                }},
                {"$group": {
                    "_id": "$bucket",
                    "traffic": {"$sum": 1},
                    "errors": {
                        "$sum": {
                            "$cond": [{"$gte": ["$status_code", 400]}, 1, 0]
                        }
                    },
                    "avg_latency": {"$avg": "$latency_ms"}
                }},
                {"$sort": {"_id": 1}}
            ]
            buckets_data = await db.api_logs.aggregate(pipeline).to_list(None)
            for b in buckets_data:
                b_dt = b["_id"]
                if b_dt.tzinfo is None:
                    b_dt = b_dt.replace(tzinfo=timezone.utc)
                data_map[b_dt] = b
        except Exception:
            pass

    labels = []
    traffic = []
    errors = []
    latency = []

    curr = start_dt
    if unit == "minute":
        curr = curr.replace(second=0, microsecond=0)
    elif unit == "hour":
        curr = curr.replace(minute=0, second=0, microsecond=0)
    elif unit == "day":
        curr = curr.replace(hour=0, minute=0, second=0, microsecond=0)
    elif unit == "month":
        curr = curr.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    loop_count = 0
    while curr <= end_dt and loop_count < 100:
        matched = None
        for b_time, b_val in data_map.items():
            if abs((b_time - curr).total_seconds()) < step_sec / 2:
                matched = b_val
                break

        vn_curr = curr.astimezone(vn_tz)
        labels.append(vn_curr.strftime(fmt))

        if matched:
            traffic.append(matched["traffic"])
            errors.append(matched["errors"])
            latency.append(round(matched["avg_latency"] or 0, 1))
        else:
            traffic.append(0)
            errors.append(0)
            latency.append(0)

        loop_count += 1
        if unit == "month":
            nm = curr.month + 1
            ny = curr.year
            if nm > 12:
                nm = 1
                ny += 1
            curr = curr.replace(year=ny, month=nm)
        else:
            curr += timedelta(seconds=step_sec)

    return {
        "range": r_val,
        "interval": iv_val or unit,
        "mode": mode_val,
        "labels": labels,
        "traffic": traffic,
        "errors": errors,
        "latency": latency,
        "total_traffic": sum(traffic),
        "total_errors": sum(errors),
        "avg_latency": round(sum(latency) / max(1, sum(1 for lat_val in latency if lat_val > 0)), 1)
    }


# --- 8. API USAGE REPORT LOGS FOR STAFF REPORT PAGE ---

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

    catalog = await endpoint_repository.list_endpoints()
    catalog_paths = {
        endpoint.get("path") or endpoint.get("endpoint_id")
        for endpoint in catalog.values()
        if endpoint.get("endpoint_id") or endpoint.get("path")
    }
    query: Dict = {"path": {"$in": list(catalog_paths)}}

    if status:
        if status == "200":
            query["status_code"] = {"$gte": 200, "$lt": 300}
        elif status == "400":
            query["status_code"] = {"$gte": 400, "$lt": 500}
        elif status == "500":
            query["status_code"] = {"$gte": 500, "$lt": 600}

    if api:
        if api not in catalog_paths:
            return {
                "object": "list",
                "data": [],
                "total": 0,
                "page": page,
                "page_size": page_size,
            }
        query["path"] = api

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

    total = await db.api_logs.count_documents(query)
    skip = (page - 1) * page_size
    cursor = db.api_logs.find(query, {"_id": 0}).sort("timestamp", -1).skip(skip).limit(page_size)
    logs = await cursor.to_list(length=page_size)

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
            result = [log_item for log_item in result if 200 <= log_item.get("status_code", 0) < 300]
        elif status == "400":
            result = [log_item for log_item in result if 400 <= log_item.get("status_code", 0) < 500]
        elif status == "500":
            result = [log_item for log_item in result if 500 <= log_item.get("status_code", 0) < 600]
    if api:
        result = [log_item for log_item in result if log_item.get("path") == api]
    if from_date:
        clean = from_date.replace("/", "-")
        result = [log_item for log_item in result if log_item.get("timestamp", "") >= f"{clean}T00:00:00"]
    if to_date:
        clean = to_date.replace("/", "-")
        result = [log_item for log_item in result if log_item.get("timestamp", "") <= f"{clean}T23:59:59"]
    return result
