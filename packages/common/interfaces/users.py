from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List


class IUserRepository(ABC):
    """Abstract Repository Interface for User Management & RBAC Credentials."""

    @abstractmethod
    async def create_user(self, user_record: Dict[str, Any]) -> Dict[str, Any]:
        pass

    @abstractmethod
    async def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        pass

    @abstractmethod
    async def get_user_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        pass

    @abstractmethod
    async def update_user(self, user_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        pass

    @abstractmethod
    async def list_users(self) -> List[Dict[str, Any]]:
        pass
