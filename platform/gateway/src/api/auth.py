from typing import Optional
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


class ForgotPasswordRequest(BaseModel):
    email: str = Field(..., json_schema_extra={"example": "dev_namle@company.com"})
    new_password: str = Field(..., json_schema_extra={"example": "newsecret123"})


@router.post("/forgot-password", summary="Reset Account Password")
async def forgot_password(request: ForgotPasswordRequest, http_req: Request):
    success = await auth_service.reset_password(email=request.email, new_password=request.new_password)
    if not success:
        raise HTTPException(status_code=404, detail="User account with this email not found.")

    client_ip = http_req.client.host if http_req.client else "127.0.0.1"
    await audit_service.log_event(
        actor=request.email,
        action="USER_PASSWORD_RESET",
        resource="Account Security",
        details=f"Password reset completed for '{request.email}'.",
        ip_address=client_ip,
    )

    return {"message": "Password updated successfully. Please log in with your new password."}


import httpx

from src.configs.settings import gateway_settings

GOOGLE_CLIENT_ID = gateway_settings.google_client_id
GOOGLE_CLIENT_SECRET = (
    gateway_settings.google_client_secret.get_secret_value() if gateway_settings.google_client_secret else ""
)


class GoogleAuthRequest(BaseModel):
    credential: Optional[str] = None
    access_token: Optional[str] = None
    code: Optional[str] = None
    redirect_uri: Optional[str] = None
    email: Optional[str] = None
    name: Optional[str] = None
    picture: Optional[str] = None


@router.get("/google/config", summary="Get Google OAuth Client ID Configuration")
async def get_google_config():
    return {
        "client_id": GOOGLE_CLIENT_ID,
    }


@router.post("/google", summary="Google OAuth 2.0 Sign In / SSO")
async def google_login(request: GoogleAuthRequest, http_req: Request):
    user_info = None

    async with httpx.AsyncClient(timeout=10.0) as client:
        # Case 1: Authorization Code exchange
        if request.code:
            try:
                token_resp = await client.post(
                    "https://oauth2.googleapis.com/token",
                    data={
                        "code": request.code,
                        "client_id": GOOGLE_CLIENT_ID,
                        "client_secret": GOOGLE_CLIENT_SECRET,
                        "redirect_uri": request.redirect_uri or "http://localhost:5173/auth/login.html",
                        "grant_type": "authorization_code",
                    },
                )
                if token_resp.status_code == 200:
                    token_data = token_resp.json()
                    access_token = token_data.get("access_token")
                    if access_token:
                        u_resp = await client.get(
                            "https://www.googleapis.com/oauth2/v3/userinfo",
                            headers={"Authorization": f"Bearer {access_token}"},
                        )
                        if u_resp.status_code == 200:
                            user_info = u_resp.json()
            except Exception:
                pass

        # Case 2: Access Token verification
        if not user_info and request.access_token:
            try:
                u_resp = await client.get(
                    "https://www.googleapis.com/oauth2/v3/userinfo",
                    headers={"Authorization": f"Bearer {request.access_token}"},
                )
                if u_resp.status_code == 200:
                    user_info = u_resp.json()
            except Exception:
                pass

        # Case 3: Google ID Token (credential) verification
        if not user_info and request.credential:
            try:
                t_resp = await client.get(
                    f"https://oauth2.googleapis.com/tokeninfo?id_token={request.credential}"
                )
                if t_resp.status_code == 200:
                    user_info = t_resp.json()
            except Exception:
                pass

    # Fallback to direct client profile if available
    if not user_info and request.email:
        user_info = {
            "email": request.email,
            "name": request.name or request.email.split("@")[0].title(),
            "picture": request.picture,
        }

    if not user_info or not user_info.get("email"):
        raise HTTPException(status_code=400, detail="Xác thực tài khoản Google không thành công. Token hoặc mã ủy quyền không hợp lệ.")

    email = user_info["email"]
    name = user_info.get("name") or email.split("@")[0].title()
    picture = user_info.get("picture")

    user = await auth_service.get_or_create_oauth_user(
        email=email,
        full_name=name,
        avatar_url=picture,
        provider="google"
    )

    client_ip = http_req.client.host if http_req.client else "127.0.0.1"
    await audit_service.log_event(
        actor=user["email"],
        action="USER_LOGIN_GOOGLE",
        resource="Google OAuth2 SSO",
        details=f"User '{user['email']}' logged in via Google SSO (prompt=select_account).",
        ip_address=client_ip,
    )

    return {
        "message": "Đăng nhập Google thành công.",
        "user": user,
        "access_token": f"aip_session_{user['user_id']}",
    }
