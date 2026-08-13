from datetime import datetime

from fastapi import APIRouter

router = APIRouter(prefix="/admin/v1", tags=["Admin - SIEM Audit Logs"])

_MOCK_AUDIT_LOGS = [
    {
        "event_id": "aud_01HXEXAMPLE",
        "action": "API_KEY_CREATED",
        "actor": "admin_user_01",
        "tenant_id": "TENANT_RETAIL_BANK",
        "timestamp": datetime.utcnow().isoformat(),
        "source_ip": "10.0.1.45"
    }
]


@router.get("/audit")
async def get_audit_logs():
    return {
        "object": "list",
        "data": _MOCK_AUDIT_LOGS
    }
