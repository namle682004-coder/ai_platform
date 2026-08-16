from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List


class IProjectRepository(ABC):
    """Abstract Repository Interface for User Projects."""

    @abstractmethod
    async def create_project(self, project_record: Dict[str, Any]) -> Dict[str, Any]:
        pass

    @abstractmethod
    async def list_user_projects(self, user_id: str) -> List[Dict[str, Any]]:
        pass

    @abstractmethod
    async def get_project(self, project_id: str) -> Optional[Dict[str, Any]]:
        pass
