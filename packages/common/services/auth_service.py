import uuid
import hashlib
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from common.database.mongodb import mongo_manager

DEFAULT_ADMIN_USER = {
    "user_id": "user_admin_default",
    "email": "admin@company.com",
    "role": "admin",
    "full_name": "System Administrator",
    "created_at": datetime.now(timezone.utc).isoformat(),
}


class AuthService:
    """
    Staff & Admin User Authentication & Account Management Service.
    Persists users in MongoDB Atlas 'users' collection.
    """

    def __init__(self):
        self._users_cache: Dict[str, Dict[str, Any]] = {
            "admin@company.com": dict(DEFAULT_ADMIN_USER)
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
            "full_name": full_name or email.split("@")[0].title(),
            "created_at": now,
        }

        db = mongo_manager.get_database()
        if db is not None:
            try:
                await db.users.insert_one(record)
            except Exception:
                pass

        self._users_cache[email] = record
        return {
            "user_id": user_id,
            "email": email,
            "role": role,
            "full_name": record["full_name"],
            "created_at": now,
        }

    async def authenticate_user(self, email: str, password: str) -> Optional[Dict[str, Any]]:
        hashed = self._hash_password(password)

        db = mongo_manager.get_database()
        if db is not None:
            try:
                user = await db.users.find_one({"email": email, "hashed_password": hashed}, {"_id": 0, "hashed_password": 0})
                if user:
                    return user
            except Exception:
                pass

        cached = self._users_cache.get(email)
        if cached and cached.get("hashed_password") == hashed:
            user_copy = dict(cached)
            user_copy.pop("hashed_password", None)
            return user_copy

        # Default admin fallback for quick demo
        if email == "admin@company.com" and password == "admin123":
            return DEFAULT_ADMIN_USER

        return None


auth_service = AuthService()
