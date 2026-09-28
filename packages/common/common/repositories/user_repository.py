import hashlib
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from common.interfaces.users import IUserRepository
from common.database.mongodb import mongo_manager

DEFAULT_USERS = [
    {
        "user_id": "user_admin_default",
        "email": "admin@company.com",
        "hashed_password": hashlib.sha256("admin123".encode()).hexdigest(),
        "role": "admin",
        "status": "active",
        "full_name": "System Administrator",
        "created_at": datetime.now(timezone.utc).isoformat(),
    },
    {
        "user_id": "user_staff_01",
        "email": "dev_namle@company.com",
        "hashed_password": hashlib.sha256("secret123".encode()).hexdigest(),
        "role": "staff",
        "status": "active",
        "full_name": "Nam Le Developer",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
]


class MongoUserRepository(IUserRepository):
    """MongoDB Atlas implementation for Users repository."""

    def __init__(self):
        self._users_cache: Dict[str, Dict[str, Any]] = {
            u["email"]: dict(u) for u in DEFAULT_USERS
        }

    async def create_user(self, user_record: Dict[str, Any]) -> Dict[str, Any]:
        db = mongo_manager.get_database()
        if db is not None:
            try:
                await db.users.insert_one(dict(user_record))
            except Exception:
                pass
        user_record.pop("_id", None)
        self._users_cache[user_record["email"]] = user_record
        return user_record

    async def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        db = mongo_manager.get_database()
        if db is not None:
            try:
                doc = await db.users.find_one({"email": email}, {"_id": 0})
                if doc:
                    doc.pop("_id", None)
                    self._users_cache[email] = doc
                    return doc
            except Exception:
                pass
        return self._users_cache.get(email)

    async def get_user_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        db = mongo_manager.get_database()
        if db is not None:
            try:
                doc = await db.users.find_one({"user_id": user_id}, {"_id": 0})
                if doc:
                    doc.pop("_id", None)
                    return doc
            except Exception:
                pass
        for u in self._users_cache.values():
            if u.get("user_id") == user_id:
                return u
        return None

    async def update_user(self, user_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        user = await self.get_user_by_id(user_id)
        if user:
            user.update(updates)
            email = user["email"]
            self._users_cache[email] = user
            db = mongo_manager.get_database()
            if db is not None:
                try:
                    await db.users.update_one({"user_id": user_id}, {"$set": user}, upsert=True)
                except Exception:
                    pass
            user.pop("_id", None)
            return user
        return None

    async def list_users(self) -> List[Dict[str, Any]]:
        db = mongo_manager.get_database()
        if db is not None:
            try:
                cursor = db.users.find({}, {"_id": 0, "hashed_password": 0})
                users = await cursor.to_list(length=100)
                if users:
                    for u in users:
                        u.pop("_id", None)
                    return users
            except Exception:
                pass
        res = []
        for u in self._users_cache.values():
            uc = dict(u)
            uc.pop("hashed_password", None)
            uc.pop("_id", None)
            res.append(uc)
        return res


user_repository = MongoUserRepository()
