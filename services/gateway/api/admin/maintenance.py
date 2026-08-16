from fastapi import APIRouter
from pydantic import BaseModel
from typing import Dict, Any
from common.services.audit_service import audit_service

router = APIRouter(prefix="/admin/v1/maintenance", tags=["Admin - System Maintenance & Emergency Circuit Breaker"])

# In-memory circuit breaker state
_maintenance_state: Dict[str, Any] = {
    "is_maintenance": False,
    "reason": "Routine GPU Cluster Maintenance",
    "updated_by": "admin@company.com"
}


class ToggleMaintenanceRequest(BaseModel):
    is_maintenance: bool
    reason: str = "Emergency GPU Cluster Stop"


@router.get("/status", summary="Get System Maintenance Status")
async def get_maintenance_status():
    return _maintenance_state


@router.post("/toggle", summary="Toggle System Maintenance Mode (Emergency Circuit Breaker)")
async def toggle_maintenance(request: ToggleMaintenanceRequest):
    _maintenance_state["is_maintenance"] = request.is_maintenance
    _maintenance_state["reason"] = request.reason

    action = "CIRCUIT_BREAKER_ACTIVATED" if request.is_maintenance else "CIRCUIT_BREAKER_DEACTIVATED"
    await audit_service.log_event(
        actor="admin@company.com",
        action=action,
        resource="Emergency Circuit Breaker",
        details=f"System Maintenance set to {request.is_maintenance}. Reason: {request.reason}",
    )

    return {
        "message": f"Emergency Maintenance Mode set to {request.is_maintenance}.",
        "state": _maintenance_state,
    }


def is_system_in_maintenance() -> bool:
    return _maintenance_state.get("is_maintenance", False)
