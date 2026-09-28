from typing import Optional, Dict, Any, List
from common.interfaces.rate_limits import IRateLimitRepository
from common.database.mongodb import mongo_manager


class MongoRateLimitRepository(IRateLimitRepository):
    """MongoDB Atlas implementation for Custom Rate Limit Policies."""

    def __init__(self):
        self._policies_cache: Dict[str, Dict[str, Any]] = {}

    async def create_policy(self, policy_record: Dict[str, Any]) -> Dict[str, Any]:
        db = mongo_manager.get_database()
        if db is not None:
            try:
                await db.rate_limits.insert_one(dict(policy_record))
            except Exception:
                pass
        policy_record.pop("_id", None)
        self._policies_cache[policy_record["policy_id"]] = policy_record
        return policy_record

    async def get_policy(self, policy_id: str) -> Optional[Dict[str, Any]]:
        if policy_id in self._policies_cache:
            return dict(self._policies_cache[policy_id])
        db = mongo_manager.get_database()
        if db is not None:
            try:
                doc = await db.rate_limits.find_one({"policy_id": policy_id}, {"_id": 0})
                if doc:
                    doc.pop("_id", None)
                    return doc
            except Exception:
                pass
        return None

    async def list_policies(self) -> List[Dict[str, Any]]:
        db = mongo_manager.get_database()
        if db is not None:
            try:
                cursor = db.rate_limits.find({}, {"_id": 0})
                policies = await cursor.to_list(length=100)
                if policies:
                    for p in policies:
                        p.pop("_id", None)
                    return policies
            except Exception:
                pass
        return [dict(p) for p in self._policies_cache.values()]


rate_limit_repository = MongoRateLimitRepository()
