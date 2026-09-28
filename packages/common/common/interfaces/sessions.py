from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List


class ISessionRepository(ABC):
    """Abstract Repository Interface for Active User Sessions & Tokens."""

    @abstractmethod
    async def create_session(self, session_record: Dict[str, Any]) -> Dict[str, Any]:
        pass

    @abstractmethod
    async def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        pass

    @abstractmethod
    async def list_user_sessions(self, user_id: str) -> List[Dict[str, Any]]:
        pass

    @abstractmethod
    async def revoke_session(self, session_id: str) -> bool:
        pass
