"""
Shared SSRF Egress Guard for AIP Platform.
Inspired by DCP NetGuard architecture (GAP-015).

Prevents Server-Side Request Forgery (SSRF) when making outbound requests
to client-supplied URLs (e.g. webhook_url, image/audio download URLs).
Validates that URLs resolve only to publicly routable hosts and never to
private, loopback, link-local (cloud metadata), or reserved IP ranges.
"""

from __future__ import annotations

import asyncio
import ipaddress
import logging
from urllib.parse import urlsplit

logger = logging.getLogger("aip-common.netguard")


def _is_ip_blocked(raw_ip: str) -> bool:
    """Check if an IP address falls into restricted or dangerous ranges."""
    try:
        ip = ipaddress.ip_address(raw_ip)
    except ValueError:
        return True  # Unparseable IP -> unsafe by default

    return (
        ip.is_private          # 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16
        or ip.is_loopback      # 127.0.0.0/8, ::1
        or ip.is_link_local    # 169.254.0.0/16 (AWS / GCP / K8s metadata endpoints)
        or ip.is_reserved      # IETF reserved ranges
        or ip.is_multicast     # 224.0.0.0/4
        or ip.is_unspecified   # 0.0.0.0, ::
    )


async def is_safe_public_url(url: str) -> tuple[bool, str]:
    """
    Validate that a URL is safe for server-side outbound requests.

    Returns:
        tuple[bool, str]: (is_safe, error_reason)
    """
    if not isinstance(url, str) or not url.strip():
        return False, "URL không được để trống"

    parts = urlsplit(url.strip())
    if parts.scheme not in ("http", "https"):
        return False, f"Chỉ hỗ trợ giao thức http hoặc https (nhận được: '{parts.scheme}')"

    host = parts.hostname
    if not host:
        return False, "URL không chứa hostname hợp lệ"

    # Check for direct localhost / numeric loopback strings before DNS
    if host.lower() in ("localhost", "127.0.0.1", "0.0.0.0", "::1"):
        return False, f"Hostname '{host}' trỏ về loopback nội bộ bị cấm (SSRF Protection)"

    # Asynchronously resolve hostname via thread pool to avoid blocking event loop
    try:
        loop = asyncio.get_running_loop()
        addr_infos = await loop.getaddrinfo(host, None)
    except (OSError, UnicodeError, ValueError) as exc:
        logger.warning(f"Failed to resolve host '{host}' for URL '{url}': {exc}")
        return False, f"Không thể phân giải tên miền '{host}': {exc}"

    if not addr_infos:
        return False, f"Tên miền '{host}' không trả về địa chỉ IP nào"

    for info in addr_infos:
        ip_str = info[4][0]
        if _is_ip_blocked(ip_str):
            logger.warning(f"Blocked SSRF target: host '{host}' resolved to restricted IP '{ip_str}'")
            return False, f"Tên miền '{host}' phân giải về dải mạng nội bộ bị cấm '{ip_str}' (SSRF Protection)"

    return True, ""
