from abc import ABC, abstractmethod
from typing import Dict, Any, List


class IWebhookRepository(ABC):
    """Abstract Repository Interface for Tenant Webhooks."""

    @abstractmethod
    async def create_webhook(self, webhook_record: Dict[str, Any]) -> Dict[str, Any]:
        pass

    @abstractmethod
    async def list_webhooks(self, tenant_id: str) -> List[Dict[str, Any]]:
        pass

    @abstractmethod
    async def delete_webhook(self, webhook_id: str) -> bool:
        pass
