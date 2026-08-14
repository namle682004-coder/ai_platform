from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from common.services.auth_service import auth_service
from common.services.audit_service import audit_service

router = APIRouter(prefix="/v1/auth", tags=["Authentication & Staff Accounts"])


class SignupRequest(BaseModel):
    email: str = Field(..., json_schema_extra={"example": "staff_namle@company.com"})
    password: str = Field(..., json_schema_extra={"example": "secret123"})
    full_name: str = Field(..., json_schema_extra={"example": "Nam Le Developer"})
    role: str = Field("staff", json_schema_extra={"example": "staff"}, description="'staff' or 'admin'")


class LoginRequest(BaseModel):
    email: str = Field(..., json_schema_extra={"example": "admin@company.com"})
    password: str = Field(..., json_schema_extra={"example": "admin123"})


@router.post("/signup", summary="Register Staff / Admin Account")
async def signup(request: SignupRequest, http_req: Request):
    if request.role not in ["staff", "admin"]:
        raise HTTPException(status_code=400, detail="Role must be 'staff' or 'admin'.")

    user = await auth_service.register_user(
        email=request.email,
        password=request.password,
        role=request.role,
        full_name=request.full_name,
    )

    client_ip = http_req.client.host if http_req.client else "127.0.0.1"
    await audit_service.log_event(
        actor=user["email"],
        action="USER_SIGNUP",
        resource=f"Role: {user['role']}",
        details=f"New {user['role']} account registered: {user['email']}",
        ip_address=client_ip,
    )

    return {
        "message": f"Account '{user['email']}' created successfully.",
        "user": user,
    }


@router.post("/login", summary="Login Staff / Admin Account")
async def login(request: LoginRequest, http_req: Request):
    user = await auth_service.authenticate_user(email=request.email, password=request.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password.")

    client_ip = http_req.client.host if http_req.client else "127.0.0.1"
    await audit_service.log_event(
        actor=user["email"],
        action="USER_LOGIN",
        resource=f"Role: {user['role']}",
        details=f"User '{user['email']}' logged in successfully.",
        ip_address=client_ip,
    )

    return {
        "message": "Login successful.",
        "user": user,
        "access_token": f"aip_session_{user['user_id']}",
    }
