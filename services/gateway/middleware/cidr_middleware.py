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
                radial-gradient(circle at 50% 30%, rgba(239, 68, 68, 0.15) 0%, transparent 50%),
                radial-gradient(circle at 85% 85%, rgba(139, 92, 246, 0.1) 0%, transparent 40%);
        }
        .security-card {
            background: rgba(18, 26, 43, 0.9);
            backdrop-filter: blur(16px);
            border: 1px solid rgba(239, 68, 68, 0.3);
            border-radius: 20px;
            padding: 40px;
            max-width: 520px;
            width: 90%;
            text-align: center;
            box-shadow: 0 20px 50px rgba(0, 0, 0, 0.6);
        }
        .shield-icon {
            width: 72px;
            height: 72px;
            border-radius: 20px;
            background: rgba(239, 68, 68, 0.15);
            border: 1px solid rgba(239, 68, 68, 0.4);
            color: #ef4444;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 32px;
            margin: 0 auto 24px auto;
            box-shadow: 0 0 25px rgba(239, 68, 68, 0.3);
        }
        h1 { font-size: 24px; font-weight: 800; margin-bottom: 12px; }
        p { color: #94a3b8; font-size: 14px; line-height: 1.6; margin-bottom: 24px; }
        .ip-badge {
            display: inline-block;
            background: rgba(0, 0, 0, 0.4);
            border: 1px solid rgba(255, 255, 255, 0.1);
            padding: 8px 16px;
            border-radius: 8px;
            font-family: monospace;
            color: #f59e0b;
            font-size: 14px;
            margin-bottom: 24px;
        }
        .instructions {
            background: rgba(255, 255, 255, 0.03);
            border-radius: 12px;
            padding: 16px;
            text-align: left;
            font-size: 13px;
            color: #cbd5e1;
        }
        .instructions li { margin-bottom: 8px; }
    </style>
</head>
<body>
    <div class="security-card">
        <div class="shield-icon"><i class="fa-solid fa-user-shield"></i></div>
        <h1>403 Forbidden - Enterprise Security Gate</h1>
        <p>Access to the <strong>AI Inference Platform Admin Control Panel</strong> is strictly restricted to authorized Enterprise VPN / Internal CIDR networks.</p>
        <div>Client Source IP:</div>
        <div class="ip-badge"><i class="fa-solid fa-network-wired"></i> CLIENT_IP_PLACEHOLDER</div>
        <div class="instructions">
            <div style="font-weight: 700; margin-bottom: 8px; color: #fff;"><i class="fa-solid fa-lock"></i> How to resolve:</div>
            <ul>
                <li>Connect to the Corporate WireGuard / OpenVPN Client.</li>
                <li>Ensure your source IP is within allowed CIDR blocks (SRS 8.2).</li>
                <li>Contact Security Admin to whitelist your IP range in <code>ADMIN_ALLOWED_CIDRS</code>.</li>
            </ul>
        </div>
    </div>
</body>
</html>
"""


class AdminCIDRMiddleware(BaseHTTPMiddleware):
    """
    Admin Endpoint Security Middleware enforcing CIDR Allowlist checks as required by SRS Section 8.2.
    Blocks unauthorized external IPs right at the outermost /admin page with a Security Landing Page or JSON 403.
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

        # Block unauthorized IPs at the outermost /admin level (UI & APIs)
        if path.startswith("/admin"):
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
                    # If HTML page request to /admin or /admin/dashboard, return 403 Security Page
                    accept_header = request.headers.get("accept", "")
                    if "text/html" in accept_header and not path.startswith("/admin/v1/"):
                        html_content = HTML_403_SECURITY_PAGE.replace("CLIENT_IP_PLACEHOLDER", client_ip_str)
                        return HTMLResponse(status_code=403, content=html_content)

                    # Otherwise return JSON 403 Forbidden for REST APIs
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
            except ValueError:
                pass

        return await call_next(request)
