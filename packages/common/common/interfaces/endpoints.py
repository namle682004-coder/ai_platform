from abc import ABC, abstractmethod
from typing import Optional, Dict, Any


class IEndpointRepository(ABC):
    """Abstract Repository Interface for Export Endpoints & Feature Flags."""

    @abstractmethod
    async def list_endpoints(self) -> Dict[str, Any]:
        pass

    @abstractmethod
    async def update_endpoint_status(self, endpoint_id: str, status: str) -> Optional[Dict[str, Any]]:
        pass
