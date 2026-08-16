import uuid
import hashlib
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from common.repositories.user_repository import user_repository


class AuthService:
    """
    Staff & Admin User Authentication, Role-Based Access Control (RBAC), and Account Management Service.
    Leverages MongoUserRepository for domain persistence.
    """

    def __init__(self):
        self.user_repo = user_repository

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

        created = await self.user_repo.create_user(record)
        res = dict(created)
        res.pop("hashed_password", None)
        res.pop("_id", None)
        return res

    async def authenticate_user(self, email: str, password: str) -> Optional[Dict[str, Any]]:
        hashed = self._hash_password(password)
        user = await self.user_repo.get_user_by_email(email)

        if user and user.get("hashed_password") == hashed and user.get("status") == "active":
            user_copy = dict(user)
            user_copy.pop("hashed_password", None)
            user_copy.pop("_id", None)
            return user_copy

        return None

    async def reset_password(self, email: str, new_password: str) -> bool:
        user = await self.user_repo.get_user_by_email(email)
        if not user:
            return False

        hashed = self._hash_password(new_password)
        updated = await self.user_repo.update_user(user["user_id"], {"hashed_password": hashed})
        return updated is not None

    async def list_users(self) -> List[Dict[str, Any]]:
        return await self.user_repo.list_users()


auth_service = AuthService()
