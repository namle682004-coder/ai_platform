from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List


class IKeyRepository(ABC):
    """Abstract Repository Interface for API Keys & Quota management."""

    @abstractmethod
    async def create_key(self, record: Dict[str, Any]) -> Dict[str, Any]:
        pass

    @abstractmethod
    async def list_keys(self) -> List[Dict[str, Any]]:
        pass

    @abstractmethod
    async def update_quota(self, key_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        pass

    @abstractmethod
    async def delete_key(self, key_id: str) -> bool:
        pass

    @abstractmethod
    async def create_key_request(self, request_record: Dict[str, Any]) -> Dict[str, Any]:
        pass

    @abstractmethod
    async def list_pending_key_requests(self) -> List[Dict[str, Any]]:
        pass

    @abstractmethod
    async def approve_key_request(self, request_id: str) -> Optional[Dict[str, Any]]:
        pass

    @abstractmethod
    async def reject_key_request(self, request_id: str, reason: str) -> Optional[Dict[str, Any]]:
        pass


class IAliasRepository(ABC):
    """Abstract Repository Interface for Model Aliases registry."""

    @abstractmethod
    async def list_aliases(self) -> Dict[str, Any]:
        pass

    @abstractmethod
    async def update_alias_status(self, alias_name: str, status: str) -> Optional[Dict[str, Any]]:
        pass
