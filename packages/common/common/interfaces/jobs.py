from abc import ABC, abstractmethod
from typing import Optional, Dict, Any


class IJobRepository(ABC):
    """Abstract Repository Interface for Async Job Life Cycle."""

    @abstractmethod
    async def create_job(self, job_record: Dict[str, Any]) -> Dict[str, Any]:
        pass

    @abstractmethod
    async def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        pass

    @abstractmethod
    async def update_job_status(self, job_id: str, status: str, updates: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        pass
