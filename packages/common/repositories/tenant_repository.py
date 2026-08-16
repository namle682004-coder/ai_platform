from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from common.interfaces.tenants import ITenantRepository
from common.database.mongodb import mongo_manager

DEFAULT_TENANTS = [
    {
        "tenant_id": "TENANT_RETAIL_BANK",
        "name": "Retail Banking Enterprise",
        "billing_tier": "enterprise_p1",
        "contact_email": "admin@company.com",
        "status": "active",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
]


class MongoTenantRepository(ITenantRepository):
    """MongoDB Atlas implementation for Enterprise Tenant Organizations."""

    def __init__(self):
        self._tenants_cache: Dict[str, Dict[str, Any]] = {
            t["tenant_id"]: dict(t) for t in DEFAULT_TENANTS
        }

    async def create_tenant(self, tenant_record: Dict[str, Any]) -> Dict[str, Any]:
        db = mongo_manager.get_database()
        if db is not None:
            try:
                await db.tenants.insert_one(dict(tenant_record))
            except Exception:
                pass
        tenant_record.pop("_id", None)
        self._tenants_cache[tenant_record["tenant_id"]] = tenant_record
        return tenant_record

    async def get_tenant(self, tenant_id: str) -> Optional[Dict[str, Any]]:
        if tenant_id in self._tenants_cache:
            return dict(self._tenants_cache[tenant_id])
        db = mongo_manager.get_database()
        if db is not None:
            try:
                doc = await db.tenants.find_one({"tenant_id": tenant_id}, {"_id": 0})
                if doc:
                    doc.pop("_id", None)
                    self._tenants_cache[tenant_id] = doc
                    return doc
            except Exception:
                pass
        return None

    async def list_tenants(self) -> List[Dict[str, Any]]:
        db = mongo_manager.get_database()
        if db is not None:
            try:
                cursor = db.tenants.find({}, {"_id": 0})
                tenants = await cursor.to_list(length=100)
                if tenants:
                    for t in tenants:
                        t.pop("_id", None)
                    return tenants
            except Exception:
                pass
        return [dict(t) for t in self._tenants_cache.values()]

    def save_payment(self, payment_record: Dict[str, Any]) -> Dict[str, Any]:
        if not hasattr(self, "_payments_cache"):
            self._payments_cache = []
        rec = dict(payment_record)
        rec.pop("_id", None)
        self._payments_cache.insert(0, rec)
        db = mongo_manager.get_database()
        if db is not None:
            try:
                db.payments.insert_one(dict(rec))
            except Exception:
                pass
        return rec

    def list_payments(self) -> List[Dict[str, Any]]:
        if not hasattr(self, "_payments_cache"):
            self._payments_cache = []
        db = mongo_manager.get_database()
        if db is not None:
            try:
                cursor = db.payments.find({}, {"_id": 0})
                payments = list(cursor)
                if payments:
                    for p in payments:
                        p.pop("_id", None)
                    return payments
            except Exception:
                pass
        return [dict(p) for p in self._payments_cache]


tenant_repository = MongoTenantRepository()
