from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from common.interfaces.usage import IUsageRepository
from common.database.mongodb import mongo_manager


class MongoUsageRepository(IUsageRepository):
    """MongoDB Atlas implementation for AI Inference Usage Records & Token Metering."""

    def __init__(self):
        self._cache: List[Dict[str, Any]] = []

    async def record_usage(self, usage_record: Dict[str, Any]) -> Dict[str, Any]:
        """Persist inference usage record to MongoDB Atlas and update in-memory cache."""
        if "timestamp" not in usage_record:
            usage_record["timestamp"] = datetime.now(timezone.utc).isoformat()

        db = mongo_manager.get_database()
        if db is not None:
            try:
                # 1. Insert granular usage record
                await db.usage_records.insert_one(dict(usage_record))

                # 2. Asynchronously update tenant aggregated consumption
                tenant_id = usage_record.get("tenant_id", "TENANT_RETAIL_BANK")
                tokens = usage_record.get("total_tokens", 0)
                cost = usage_record.get("cost_vnd", 0.0)

                await db.tenants.update_one(
                    {"tenant_id": tenant_id},
                    {
                        "$inc": {
                            "total_tokens_consumed": tokens,
                            "total_cost_vnd": cost,
                            "total_inference_requests": 1,
                        },
                        "$set": {
                            "last_active_at": usage_record["timestamp"],
                        }
                    },
                    upsert=True,
                )
            except Exception:
                pass  # Graceful fallback on DB transient errors

        usage_record.pop("_id", None)
        self._cache.insert(0, dict(usage_record))
        if len(self._cache) > 500:
            self._cache.pop()
        return usage_record

    async def list_usage_records(
        self,
        tenant_id: Optional[str] = None,
        domain: Optional[str] = None,
        model_alias: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """List usage records matching criteria."""
        db = mongo_manager.get_database()
        if db is not None:
            try:
                query: Dict[str, Any] = {}
                if tenant_id:
                    query["tenant_id"] = tenant_id
                if domain:
                    query["domain"] = domain
                if model_alias:
                    query["model_alias"] = model_alias

                cursor = db.usage_records.find(query, {"_id": 0}).sort("timestamp", -1)
                records = await cursor.to_list(length=limit)
                if records:
                    for r in records:
                        r.pop("_id", None)
                    return records
            except Exception:
                pass

        # In-memory cache fallback
        filtered = self._cache
        if tenant_id:
            filtered = [r for r in filtered if r.get("tenant_id") == tenant_id]
        if domain:
            filtered = [r for r in filtered if r.get("domain") == domain]
        if model_alias:
            filtered = [r for r in filtered if r.get("model_alias") == model_alias]
        return filtered[:limit]

    async def get_usage_summary(
        self,
        tenant_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Aggregate total requests, tokens, and cost."""
        records = await self.list_usage_records(tenant_id=tenant_id, limit=1000)

        total_requests = len(records)
        total_prompt_tokens = sum(r.get("prompt_tokens", 0) for r in records)
        total_completion_tokens = sum(r.get("completion_tokens", 0) for r in records)
        total_tokens = sum(r.get("total_tokens", 0) for r in records)
        total_cost_vnd = round(sum(r.get("cost_vnd", 0.0) for r in records), 2)
        active_models = sorted(list({r.get("model_alias") for r in records if r.get("model_alias")}))

        return {
            "tenant_id": tenant_id or "all",
            "total_requests": total_requests,
            "total_prompt_tokens": total_prompt_tokens,
            "total_completion_tokens": total_completion_tokens,
            "total_tokens": total_tokens,
            "total_cost_vnd": total_cost_vnd,
            "active_models": active_models,
        }


usage_repository = MongoUsageRepository()
