from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from common.services.auth_service import auth_service
from common.services.audit_service import audit_service

router = APIRouter(prefix="/admin/v1/users", tags=["Admin - User & RBAC Governance"])


class UpdateStatusRequest(BaseModel):
    status: str = Field(..., json_schema_extra={"example": "locked"}, description="'active' or 'locked'")


class UpdateRoleRequest(BaseModel):
    role: str = Field(..., json_schema_extra={"example": "admin"}, description="'admin', 'staff', or 'manager'")


@router.get("", summary="List Registered Users (Admin Only)")
async def list_users():
    users = await auth_service.list_users()
    return {"object": "list", "data": users}


@router.put("/{user_id}/status", summary="Lock or Unlock User Account (Admin Only)")
async def update_user_status(user_id: str, request: UpdateStatusRequest):
    if request.status not in ["active", "locked"]:
        raise HTTPException(status_code=400, detail="Status must be 'active' or 'locked'.")

    updated = await auth_service.update_user_status(user_id, request.status)
    if not updated:
        raise HTTPException(status_code=404, detail=f"User ID '{user_id}' not found.")

    await audit_service.log_event(
        actor="admin@company.com",
        action="USER_STATUS_UPDATED",
        resource=f"User: {updated['email']}",
        details=f"Account status set to '{request.status}'",
    )

    return {"message": f"User status updated to '{request.status}'.", "user": updated}


@router.put("/{user_id}/role", summary="Update User Role / RBAC Permission (Admin Only)")
async def update_user_role(user_id: str, request: UpdateRoleRequest):
    if request.role not in ["admin", "staff", "manager"]:
        raise HTTPException(status_code=400, detail="Role must be 'admin', 'staff', or 'manager'.")

    updated = await auth_service.update_user_role(user_id, request.role)
    if not updated:
        raise HTTPException(status_code=404, detail=f"User ID '{user_id}' not found.")

    await audit_service.log_event(
        actor="admin@company.com",
        action="USER_ROLE_UPDATED",
        resource=f"User: {updated['email']}",
        details=f"Role changed to '{request.role}'",
    )

    return {"message": f"User role updated to '{request.role}'.", "user": updated}
