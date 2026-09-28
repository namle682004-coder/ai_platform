from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List


class IRateLimitRepository(ABC):
    """Abstract Repository Interface for Custom Rate Limit Policies."""

    @abstractmethod
    async def create_policy(self, policy_record: Dict[str, Any]) -> Dict[str, Any]:
        pass

    @abstractmethod
    async def get_policy(self, policy_id: str) -> Optional[Dict[str, Any]]:
        pass

    @abstractmethod
    async def list_policies(self) -> List[Dict[str, Any]]:
        pass
