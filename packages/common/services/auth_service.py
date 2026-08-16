import uuid
import hashlib
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
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


class AuthService:
    """
    Staff & Admin User Authentication, Role-Based Access Control (RBAC), and Account Management Service.
    Persists users in MongoDB Atlas 'users' collection.
    """

    def __init__(self):
        self._users_cache: Dict[str, Dict[str, Any]] = {
            u["email"]: dict(u) for u in DEFAULT_USERS
        }

    def _hash_password(self, password: str) -> str:
        return hashlib.sha256(password.encode()).hexdigest()

    async def register_user(self, email: str, password: str, role: str = "staff", full_name: str = "") -> Dict[str, Any]:
        user_id = f"user_{uuid.uuid4().hex[:10]}"
        now = datetime.now(timezone.utc).isoformat()
        record = {
            "user_id": user_id,
            "email": email,
            "hashed_password": self._hash_password(password),
            "role": role,
            "status": "active",
            "full_name": full_name or email.split("@")[0].title(),
            "created_at": now,
        }

        db = mongo_manager.get_database()
        if db is not None:
            try:
                await db.users.insert_one(dict(record))
            except Exception:
                pass

        record.pop("_id", None)
        self._users_cache[email] = record
        res = dict(record)
        res.pop("hashed_password", None)
        res.pop("_id", None)
        return res

    async def authenticate_user(self, email: str, password: str) -> Optional[Dict[str, Any]]:
        hashed = self._hash_password(password)

        db = mongo_manager.get_database()
        if db is not None:
            try:
                user = await db.users.find_one({"email": email, "hashed_password": hashed, "status": "active"}, {"_id": 0, "hashed_password": 0})
                if user:
                    user.pop("_id", None)
                    return user
            except Exception:
                pass

        cached = self._users_cache.get(email)
        if cached and cached.get("hashed_password") == hashed and cached.get("status") == "active":
            user_copy = dict(cached)
            user_copy.pop("hashed_password", None)
            user_copy.pop("_id", None)
            return user_copy

        return None

    async def reset_password(self, email: str, new_password: str) -> bool:
        hashed = self._hash_password(new_password)
        db = mongo_manager.get_database()
        if db is not None:
            try:
                res = await db.users.update_one({"email": email}, {"$set": {"hashed_password": hashed}})
                if res.modified_count > 0:
                    return True
            except Exception:
                pass

        if email in self._users_cache:
            self._users_cache[email]["hashed_password"] = hashed
            return True
        return False

    async def list_users(self) -> List[Dict[str, Any]]:
        db = mongo_manager.get_database()
        if db is not None:
            try:
                cursor = db.users.find({}, {"_id": 0, "hashed_password": 0})
                users = await cursor.to_list(length=100)
                if users:
                    return users
            except Exception:
                pass

        result = []
        for u in self._users_cache.values():
            cp = dict(u)
            cp.pop("hashed_password", None)
            result.append(cp)
        return result

    async def update_user_status(self, user_id: str, status: str) -> Optional[Dict[str, Any]]:
        db = mongo_manager.get_database()
        if db is not None:
            try:
                await db.users.update_one({"user_id": user_id}, {"$set": {"status": status}})
            except Exception:
                pass

        for _email, u in self._users_cache.items():
            if u["user_id"] == user_id:
                u["status"] = status
                cp = dict(u)
                cp.pop("hashed_password", None)
                return cp
        return None

    async def update_user_role(self, user_id: str, role: str) -> Optional[Dict[str, Any]]:
        db = mongo_manager.get_database()
        if db is not None:
            try:
                await db.users.update_one({"user_id": user_id}, {"$set": {"role": role}})
            except Exception:
                pass

        for _email, u in self._users_cache.items():
            if u["user_id"] == user_id:
                u["role"] = role
                cp = dict(u)
                cp.pop("hashed_password", None)
                return cp
        return None


auth_service = AuthService()
