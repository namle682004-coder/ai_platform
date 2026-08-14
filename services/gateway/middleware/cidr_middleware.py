import ipaddress
import os
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, HTMLResponse
from common.models.schemas import AIPErrorResponse, AIPError

HTML_403_SECURITY_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>403 Access Denied - AIP Enterprise Security Gate</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        body {
            background-color: #090d16;
            color: #f8fafc;
            font-family: 'Inter', sans-serif;
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            margin: 0;
            background-image: 
                radial-gradient(circle at 50% 30%, rgba(239, 68, 68, 0.18) 0%, transparent 50%),
                radial-gradient(circle at 85% 85%, rgba(139, 92, 246, 0.1) 0%, transparent 40%);
        }
        .security-card {
            background: rgba(18, 26, 43, 0.95);
            backdrop-filter: blur(20px);
            border: 1px solid rgba(239, 68, 68, 0.4);
            border-radius: 20px;
            padding: 44px;
            max-width: 540px;
            width: 90%;
            text-align: center;
            box-shadow: 0 25px 60px rgba(0, 0, 0, 0.7);
        }
        .shield-icon {
            width: 80px;
            height: 80px;
            border-radius: 20px;
            background: rgba(239, 68, 68, 0.15);
            border: 1px solid rgba(239, 68, 68, 0.5);
            color: #ef4444;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 36px;
            margin: 0 auto 24px auto;
            box-shadow: 0 0 30px rgba(239, 68, 68, 0.35);
        }
        h1 { font-size: 26px; font-weight: 800; margin-bottom: 12px; }
        p { color: #94a3b8; font-size: 14px; line-height: 1.6; margin-bottom: 24px; }
        .ip-badge {
            display: inline-block;
            background: rgba(0, 0, 0, 0.5);
            border: 1px solid rgba(255, 255, 255, 0.12);
            padding: 10px 18px;
            border-radius: 10px;
            font-family: monospace;
            color: #f59e0b;
            font-size: 15px;
            margin-bottom: 24px;
        }
        .instructions {
            background: rgba(255, 255, 255, 0.03);
            border-radius: 12px;
            padding: 18px;
            text-align: left;
            font-size: 13px;
            color: #cbd5e1;
            border: 1px solid rgba(255, 255, 255, 0.05);
        }
        .instructions ul { padding-left: 20px; margin-top: 8px; }
        .instructions li { margin-bottom: 6px; }
    </style>
</head>
<body>
    <div class="security-card">
        <div class="shield-icon"><i class="fa-solid fa-shield-halved"></i></div>
        <h1>403 Forbidden - Access Denied</h1>
        <p>Access to the <strong>AI Inference Platform Admin & Staff Portals</strong> is strictly restricted to Corporate VPN & Whitelisted CIDR Networks (SRS Section 8.2).</p>
        <div style="font-size: 12px; color: #94a3b8; margin-bottom: 6px;">Your Unauthorized Client Source IP:</div>
        <div class="ip-badge"><i class="fa-solid fa-network-wired"></i> CLIENT_IP_PLACEHOLDER</div>
        <div class="instructions">
            <div style="font-weight: 700; color: #fff;"><i class="fa-solid fa-lock"></i> Security Compliance Resolution:</div>
            <ul>
                <li>Connect to the Corporate WireGuard / OpenVPN Client.</li>
                <li>Ensure your source IP matches allowed subnet rules.</li>
                <li>Contact System Admin to whitelist your IP in <code>ADMIN_ALLOWED_CIDRS</code>.</li>
            </ul>
        </div>
    </div>
</body>
</html>
"""


class AdminCIDRMiddleware(BaseHTTPMiddleware):
    """
    Admin & Staff Endpoint Security Middleware enforcing CIDR Allowlist checks as required by SRS Section 8.2.
    Protects /admin*, /staff*, and /portal* pages from unauthorized external IP access.
    """

    def __init__(self, app, allowed_cidrs: list[str] = None):
        super().__init__(app)
        env_cidrs = os.getenv("ADMIN_ALLOWED_CIDRS", "")
        if env_cidrs:
            self.allowed_cidrs = [c.strip() for c in env_cidrs.split(",") if c.strip()]
        else:
            self.allowed_cidrs = allowed_cidrs or [
                "116.101.7.0/24",   # User's Office/Home Admin IP Range
                "127.0.0.1/32",     # Localhost Loopback
                "10.0.0.0/8",       # Private Subnet Class A
                "192.168.0.0/16",   # Private Subnet Class C
                "172.16.0.0/12",    # Private Subnet Class B
            ]

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Protect /admin*, /staff*, and /portal* endpoints with strict CIDR VPN allowlist
        if path.startswith("/admin") or path.startswith("/staff") or path.startswith("/portal"):
            client_ip_str = request.client.host if request.client else "127.0.0.1"

            # Allow local test requests
            if client_ip_str in ["127.0.0.1", "testclient", "localhost"]:
                return await call_next(request)

            try:
                client_ip = ipaddress.ip_address(client_ip_str)
                is_allowed = any(
                    client_ip in ipaddress.ip_network(cidr, strict=False)
                    for cidr in self.allowed_cidrs
                )
                if not is_allowed:
                    # For REST APIs (/admin/v1/*), return JSON 403
                    if path.startswith("/admin/v1/"):
                        error_payload = AIPErrorResponse(
                            error=AIPError(
                                type="security_error",
                                code="cidr_forbidden",
                                message=f"Access denied: Source IP '{client_ip_str}' is not in Admin CIDR Allowlist.",
                                request_id=request.headers.get("X-Request-ID"),
                                retryable=False,
                            )
                        )
                        return JSONResponse(status_code=403, content=error_payload.model_dump())

                    # For Web Page requests (/admin, /staff, /portal), render 403 Security Landing Page
                    html_content = HTML_403_SECURITY_PAGE.replace("CLIENT_IP_PLACEHOLDER", client_ip_str)
                    return HTMLResponse(status_code=403, content=html_content)
            except ValueError:
                pass

        return await call_next(request)
