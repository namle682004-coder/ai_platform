from abc import ABC, abstractmethod
from typing import Dict, Any, List


class IAPILogRepository(ABC):
    """Abstract Repository Interface for API Request & Traffic Logs."""

    @abstractmethod
    async def log_request(self, log_record: Dict[str, Any]) -> Dict[str, Any]:
        pass

    @abstractmethod
    async def list_recent_logs(self, limit: int = 100) -> List[Dict[str, Any]]:
        pass
