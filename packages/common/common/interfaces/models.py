from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List


class IModelCatalogRepository(ABC):
    """Abstract Repository Interface for Model Catalog Metadata."""

    @abstractmethod
    async def register_model(self, model_record: Dict[str, Any]) -> Dict[str, Any]:
        pass

    @abstractmethod
    async def get_model(self, model_id: str) -> Optional[Dict[str, Any]]:
        pass

    @abstractmethod
    async def list_models(self) -> List[Dict[str, Any]]:
        pass
