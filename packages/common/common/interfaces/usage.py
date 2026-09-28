from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional


class IUsageRepository(ABC):
    """Abstract Repository Interface for Inference Usage Records & Token Metering."""

    @abstractmethod
    async def record_usage(self, usage_record: Dict[str, Any]) -> Dict[str, Any]:
        """Persist a new usage record."""
        pass

    @abstractmethod
    async def list_usage_records(
        self,
        tenant_id: Optional[str] = None,
        domain: Optional[str] = None,
        model_alias: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """List usage records matching filters."""
        pass

    @abstractmethod
    async def get_usage_summary(
        self,
        tenant_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Aggregate usage metrics: total requests, tokens, cost."""
        pass
