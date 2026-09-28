from abc import ABC, abstractmethod
from typing import Dict, Any, List


class INotificationRepository(ABC):
    """Abstract Repository Interface for System Notifications & Alerts."""

    @abstractmethod
    async def create_notification(self, notification_record: Dict[str, Any]) -> Dict[str, Any]:
        pass

    @abstractmethod
    async def list_notifications(self, user_id: str) -> List[Dict[str, Any]]:
        pass
