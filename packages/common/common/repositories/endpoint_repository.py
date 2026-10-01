from typing import Any, Dict, Optional

from common.database.mongodb import mongo_manager
from common.interfaces.endpoints import IEndpointRepository


class MongoEndpointRepository(IEndpointRepository):
    """MongoDB-backed repository for API endpoint records."""

    def __init__(self):
        self._endpoints_cache: Dict[str, Dict[str, Any]] = {}

    async def list_endpoints(self) -> Dict[str, Any]:
        db = mongo_manager.get_database()
        if db is None:
            self._endpoints_cache.clear()
            raise RuntimeError("MongoDB is unavailable; API catalog cannot be loaded")

        cursor = db.endpoints.find({}, {"_id": 0})
        endpoints = await cursor.to_list(length=None)
        self._endpoints_cache.clear()
        for endpoint in endpoints:
            endpoint_id = endpoint.get("endpoint_id")
            if endpoint_id:
                self._endpoints_cache[endpoint_id] = endpoint
        return self._endpoints_cache

    async def get_endpoint_by_id(self, identifier: str) -> Optional[Dict[str, Any]]:
        """Find a database endpoint by its UUID, API ID, or path."""
        endpoints = await self.list_endpoints()
        for endpoint in endpoints.values():
            if (
                endpoint.get("id") == identifier
                or endpoint.get("api_id") == identifier
                or endpoint.get("endpoint_id") == identifier
                or endpoint.get("path") == identifier
            ):
                return endpoint
        return None

    async def update_endpoint_status(
        self, endpoint_id: str, status: str
    ) -> Optional[Dict[str, Any]]:
        db = mongo_manager.get_database()
        if db is None:
            raise RuntimeError("MongoDB is unavailable; endpoint status cannot be updated")

        result = await db.endpoints.update_one(
            {"endpoint_id": endpoint_id}, {"$set": {"status": status}}
        )
        if not result.matched_count:
            return None

        endpoint = await db.endpoints.find_one(
            {"endpoint_id": endpoint_id}, {"_id": 0}
        )
        if endpoint is None:
            return None
        self._endpoints_cache[endpoint_id] = endpoint
        return endpoint


endpoint_repository = MongoEndpointRepository()
