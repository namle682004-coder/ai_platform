"""
Enterprise Asynchronous Usage Metering & Token Consumption Service.
Compliant with Clean Architecture DDD & SRS Section 7 & 8.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from common.repositories.usage_repository import usage_repository
from common.repositories.api_log_repository import api_log_repository
from src.db.redis import redis_service

logger = logging.getLogger("aip-usage.meter")

# Pricing: 10 VND / 1000 tokens for chat/text LLM (0.01 VND / token)
TOKEN_COST_PER_UNIT_VND: float = 0.01


class UsageMeterService:
    """
    Asynchronous Usage Metering & Token Billing Service.
    - Zero-latency execution: executed via asyncio.create_task (fire-and-forget).
    - Persists granular UsageRecord to MongoDB Atlas.
    - Updates Redis TPM window & daily aggregate consumption counters.
    - Synchronizes token information to api_logs for Staff reports.
    """

    async def record_inference_usage(
        self,
        request_id: str,
        tenant_id: str = "TENANT_RETAIL_BANK",
        cost_center: str = "CC_DIGITAL_BANKING",
        api_key_prefix: Optional[str] = None,
        domain: str = "chat",
        model_alias: str = "chat-general-standard",
        physical_model: str = "Qwen3-8B",
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        total_tokens: int = 0,
        latency_ms: float = 0.0,
        status_code: int = 200,
        stream: bool = False,
        client_ip: str = "unknown",
        app_state: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Fire-and-forget asynchronous usage recording."""
        now_dt = datetime.now(timezone.utc)
        now_iso = now_dt.isoformat()
        date_str = now_dt.strftime("%Y-%m-%d")

        if total_tokens == 0:
            total_tokens = prompt_tokens + completion_tokens

        cost_vnd = round(total_tokens * TOKEN_COST_PER_UNIT_VND, 2)

        usage_doc = {
            "usage_id": f"usg_{now_dt.strftime('%y%m%d')}_{request_id[-8:] if len(request_id) >= 8 else request_id}",
            "request_id": request_id,
            "tenant_id": tenant_id,
            "cost_center": cost_center,
            "api_key_prefix": api_key_prefix,
            "domain": domain,
            "model_alias": model_alias,
            "physical_model": physical_model,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "cost_vnd": cost_vnd,
            "latency_ms": latency_ms,
            "status_code": status_code,
            "stream": stream,
            "timestamp": now_iso,
        }

        # 1. MongoDB Persistence to usage_records
        try:
            await usage_repository.record_usage(usage_doc)
        except Exception as exc:
            logger.warning(f"Failed to persist usage record: {exc}")

        # 2. Redis Counters (TPM & Daily Aggregate for Tenant)
        try:
            client = redis_service.get_client()
            if client:
                minute_ts = int(time.time() // 60) * 60
                pipe = client.pipeline()
                # Tokens Per Minute counter for tenant
                tpm_key = f"aip:tpm:{tenant_id}:{minute_ts}"
                pipe.incrby(tpm_key, max(1, total_tokens))
                pipe.expire(tpm_key, 120)

                # Daily token aggregate counter
                daily_tokens_key = f"aip:usage:tokens:{tenant_id}:{date_str}"
                pipe.incrby(daily_tokens_key, max(1, total_tokens))
                pipe.expire(daily_tokens_key, 86400 * 7)

                # Daily requests aggregate counter
                daily_req_key = f"aip:usage:requests:{tenant_id}:{date_str}"
                pipe.incr(daily_req_key)
                pipe.expire(daily_req_key, 86400 * 7)

                await pipe.execute()
        except Exception as exc:
            logger.warning(f"Failed to update Redis usage counters: {exc}")

        # 3. Synchronize token usage with MongoDB api_logs for Staff Report
        try:
            log_record = {
                "request_id": request_id,
                "method": "POST",
                "path": f"/v1/{domain}/completions" if domain == "chat" else f"/v1/{domain}",
                "status_code": status_code,
                "latency_ms": latency_ms,
                "client_ip": client_ip,
                "user_agent": "AIP-Inference-Client",
                "api_key_prefix": api_key_prefix,
                "model": model_alias,
                "tenant_id": tenant_id,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
                "cost_vnd": cost_vnd,
                "timestamp": now_iso,
            }
            await api_log_repository.log_request(log_record)
        except Exception as exc:
            logger.warning(f"Failed to sync usage to api_logs: {exc}")

        return usage_doc


usage_meter = UsageMeterService()
