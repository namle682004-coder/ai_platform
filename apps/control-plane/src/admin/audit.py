from fastapi import APIRouter
from common.services.audit_service import audit_service

router = APIRouter(prefix="/admin/v1", tags=["Admin - Security & Audit Logs"])


@router.get("/audit-logs", summary="List Security & Action Audit Logs (Admin Only)")
async def list_audit_logs():
    logs = await audit_service.get_logs(limit=100)
    return {"object": "list", "data": logs}
