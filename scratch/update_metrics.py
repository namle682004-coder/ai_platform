import re

path = "platform/gateway/src/metrics.py"
with open(path, "r", encoding="utf-8") as f:
    content = f.read()

# Replace should_log block
old_block = """            # Log API calls to MongoDB (non-blocking, fire-and-forget)
            should_log = _should_log_api_call(path)
            if should_log:
                client_ip = request.client.host if request.client else "unknown"
                log_record = {
                    "request_id": request_id,
                    "method": request.method,
                    "path": path,
                    "status_code": response.status_code,
                    "latency_ms": latency_ms,
                    "client_ip": client_ip,
                    "user_agent": request.headers.get("user-agent", ""),
                    "api_key_prefix": (request.headers.get("authorization", "")[:20] + "...") if request.headers.get("authorization") else None,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                # Fire-and-forget: don't block the response
                asyncio.create_task(_safe_log(log_record))

            return response
        finally:
            AIP_HTTP_INFLIGHT_REQUESTS.dec()


async def _safe_log(log_record: dict):
    """Log API request to MongoDB without blocking or crashing on failure."""
    try:
        from common.repositories.api_log_repository import api_log_repository
        await api_log_repository.log_request(log_record)
    except Exception:
        pass  # Never crash the request pipeline for logging failures"""

new_block = """            # Log API calls to MongoDB (non-blocking, fire-and-forget)
            should_log = _should_log_api_call(path)
            if should_log:
                client_ip = request.client.host if request.client else "unknown"
                user_id = getattr(request.state, "user_id", None) or request.headers.get("x-user-id") or request.headers.get("X-User-Id")
                if not user_id:
                    auth = request.headers.get("authorization") or request.headers.get("Authorization", "")
                    if auth.startswith("Bearer aip_session_"):
                        user_id = auth.replace("Bearer aip_session_", "").strip()
                    else:
                        user_id = "user_staff_01"
                tenant_id = getattr(request.state, "tenant_id", None) or request.headers.get("x-tenant-id") or request.headers.get("X-Tenant-Id") or "global"

                log_record = {
                    "request_id": request_id,
                    "method": request.method,
                    "path": path,
                    "status_code": response.status_code,
                    "latency_ms": latency_ms,
                    "client_ip": client_ip,
                    "user_id": user_id,
                    "tenant_id": tenant_id,
                    "user_agent": request.headers.get("user-agent", ""),
                    "api_key_prefix": (request.headers.get("authorization", "")[:20] + "...") if request.headers.get("authorization") else None,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                # Fire-and-forget: don't block the response
                asyncio.create_task(_safe_log(log_record, user_id, response.status_code))

            return response
        finally:
            AIP_HTTP_INFLIGHT_REQUESTS.dec()


async def _safe_log(log_record: dict, user_id: str, status_code: int):
    """Log API request to MongoDB and decrement token/credit balance without blocking."""
    try:
        from common.repositories.api_log_repository import api_log_repository
        await api_log_repository.log_request(log_record)

        if status_code < 400:
            from common.repositories.api_subscription_repository import api_subscription_repository
            path = log_record.get("path", "")
            # Deduct tokens or credits based on API domain
            if "/chat" in path or "/completions" in path or "/rag" in path:
                deduct_units = 15
            elif "/audio" in path:
                deduct_units = 10
            else:
                deduct_units = 1
            await api_subscription_repository.deduct_user_balance(user_id, deduct_units)
    except Exception:
        pass  # Never crash the request pipeline for logging failures"""

# Normalize newlines
content_norm = content.replace("\r\n", "\n")
old_norm = old_block.replace("\r\n", "\n")
new_norm = new_block.replace("\r\n", "\n")

if old_norm in content_norm:
    updated = content_norm.replace(old_norm, new_norm)
    with open(path, "w", encoding="utf-8") as f:
        f.write(updated)
    print("Updated metrics.py successfully!")
else:
    print("Could not find old block in metrics.py!")

