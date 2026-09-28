from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List


class ITenantRepository(ABC):
    """Abstract Repository Interface for Enterprise Tenant Organizations."""

    @abstractmethod
    async def create_tenant(self, tenant_record: Dict[str, Any]) -> Dict[str, Any]:
        pass

    @abstractmethod
    async def get_tenant(self, tenant_id: str) -> Optional[Dict[str, Any]]:
        pass

    @abstractmethod
    async def list_tenants(self) -> List[Dict[str, Any]]:
        pass
