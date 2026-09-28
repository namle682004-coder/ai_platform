import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from common.repositories.mongo_repositories import audit_repository

logger = logging.getLogger("aip-audit")


async def log_security_event(
    event_type: str,
    action: str,
    actor: str,
    details: Optional[Dict[str, Any]] = None,
    ip_address: Optional[str] = None,
) -> bool:
    try:
        record = {
            "event_type": event_type,
            "action": action,
            "actor": actor,
            "details": details or {},
            "ip_address": ip_address or "internal",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        await audit_repository.create_audit_log(record)
        return True
    except Exception as exc:
        logger.warning(f"Failed to persist audit log: {exc}")
        return False
