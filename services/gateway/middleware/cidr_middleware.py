import ipaddress
import logging
from typing import List
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, HTMLResponse
from gateway.core.config import gateway_settings
from gateway.api.admin.maintenance import is_system_in_maintenance

logger = logging.getLogger("aip-cidr-security")

HTML_403_SECURITY_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>403 Forbidden - VPN Required</title>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@400;600;700&family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
    <style>
        body { background: #060913; color: #f8fafc; font-family: 'Inter', sans-serif; height: 100vh; display: flex; align-items: center; justify-content: center; margin: 0; }
        .card { background: rgba(15, 23, 42, 0.8); border: 1px solid rgba(244, 63, 94, 0.3); border-radius: 20px; padding: 40px; text-align: center; max-width: 480px; backdrop-filter: blur(16px); }
        .icon { font-size: 48px; color: #f43f5e; margin-bottom: 16px; }
        h1 { font-family: 'Outfit', sans-serif; font-size: 24px; margin-bottom: 12px; }
        p { color: #94a3b8; font-size: 14px; line-height: 1.6; margin-bottom: 24px; }
        .pill { display: inline-block; padding: 8px 16px; border-radius: 20px; background: rgba(244, 63, 94, 0.15); color: #f43f5e; font-weight: 700; font-size: 13px; }
    </style>
</head>
<body>
    <div class="card">
        <div class="icon">🛡️</div>
        <h1>403 Access Denied</h1>
        <p>Your IP address is outside the allowed Corporate VPN / Network CIDR range. Please connect to Corporate VPN to access Admin Console or Staff Portal.</p>
        <div class="pill">SECURED BY AIP GATEWAY</div>
    </div>
</body>
</html>"""

HTML_503_MAINTENANCE_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>503 Service Maintenance</title>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@400;600;700&family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
    <style>
        body { background: #f8fafc; color: #0f172a; font-family: 'Inter', sans-serif; height: 100vh; display: flex; align-items: center; justify-content: center; margin: 0; }
        .card { background: #ffffff; border: 1px solid #e2e8f0; border-radius: 20px; padding: 40px; text-align: center; max-width: 480px; box-shadow: 0 10px 25px rgba(0,0,0,0.05); }
        .icon { font-size: 48px; color: #f59e0b; margin-bottom: 16px; }
        h1 { font-family: 'Outfit', sans-serif; font-size: 24px; margin-bottom: 12px; }
        p { color: #64748b; font-size: 14px; line-height: 1.6; margin-bottom: 24px; }
        .pill { display: inline-block; padding: 8px 16px; border-radius: 20px; background: #fffbeb; color: #b45309; font-weight: 700; font-size: 13px; }
    </style>
</head>
<body>
    <div class="card">
        <div class="icon">⚠️</div>
        <h1>503 Emergency Maintenance</h1>
        <p>The AI Platform is currently undergoing scheduled GPU maintenance or Emergency Circuit Breaker testing. Service will resume shortly.</p>
        <div class="pill">EMERGENCY CIRCUIT BREAKER ACTIVE</div>
    </div>
</body>
</html>"""


class AdminCIDRMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        self.allowed_cidrs = self._parse_cidrs(gateway_settings.admin_allowed_cidrs)

    def _parse_cidrs(self, cidr_str: str) -> List[ipaddress.IPv4Network | ipaddress.IPv6Network]:
        cidrs = []
        for item in cidr_str.split(","):
            item = item.strip()
            if item:
                try:
                    cidrs.append(ipaddress.ip_network(item, strict=False))
                except ValueError:
                    logger.warning(f"Invalid CIDR configured: {item}")
        return cidrs

    def _is_ip_allowed(self, client_host: str) -> bool:
        if client_host in ["testclient", "127.0.0.1", "localhost", "::1"]:
            return True
        if not self.allowed_cidrs:
            return True
        try:
            ip = ipaddress.ip_address(client_host)
            return any(ip in net for net in self.allowed_cidrs)
        except ValueError:
            return False

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Circuit Breaker Check
        if is_system_in_maintenance() and not path.startswith("/admin") and path not in ["/health", "/status"]:
            if "text/html" in request.headers.get("accept", ""):
                return HTMLResponse(status_code=503, content=HTML_503_MAINTENANCE_PAGE)
            return JSONResponse(status_code=503, content={"error": {"message": "Service in Emergency Maintenance Mode.", "type": "circuit_breaker"}})

        # CIDR Allowlist Protection for Admin / Staff
        if path.startswith("/admin") or path.startswith("/staff") or path.startswith("/portal"):
            client_host = request.client.host if request.client else "127.0.0.1"
            if not self._is_ip_allowed(client_host):
                logger.warning(f"Blocked unauthorized visit to {path} from IP {client_host}")
                if "text/html" in request.headers.get("accept", ""):
                    return HTMLResponse(status_code=403, content=HTML_403_SECURITY_PAGE)
                return JSONResponse(status_code=403, content={"error": {"message": f"IP {client_host} blocked by CIDR allowlist.", "type": "cidr_access_denied"}})

        return await call_next(request)
