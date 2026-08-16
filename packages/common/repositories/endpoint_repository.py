from typing import Optional, Dict, Any
from common.interfaces.endpoints import IEndpointRepository
from common.database.mongodb import mongo_manager

DEFAULT_ENDPOINTS = [
    {
        "endpoint_id": "/v1/chat/completions",
        "name": "Chat Completions API",
        "status": "enabled",
        "description": "Standard OpenAI-compatible Chat completion interface",
    },
    {
        "endpoint_id": "/v1/audio/transcriptions",
        "name": "Speech to Text API",
        "status": "enabled",
        "description": "PhoWhisper ASR Speech-to-Text inference endpoint",
    },
    {
        "endpoint_id": "/v1/audio/speech",
        "name": "Text to Speech API",
        "status": "enabled",
        "description": "VieTTS Text-to-Speech synthesis endpoint",
    },
    {
        "endpoint_id": "/v1/moderation/text",
        "name": "Content Moderation API",
        "status": "enabled",
        "description": "AI Content Safety & Toxic Filter endpoint",
    },
]


class MongoEndpointRepository(IEndpointRepository):
    """MongoDB Atlas implementation for Export Endpoints & Feature Flags."""

    def __init__(self):
        self._endpoints_cache: Dict[str, Dict[str, Any]] = {
            e["endpoint_id"]: dict(e) for e in DEFAULT_ENDPOINTS
        }

    async def list_endpoints(self) -> Dict[str, Any]:
        db = mongo_manager.get_database()
        if db is not None:
            try:
                cursor = db.endpoints.find({}, {"_id": 0})
                eps = await cursor.to_list(length=100)
                if eps:
                    for item in eps:
                        item.pop("_id", None)
                        self._endpoints_cache[item["endpoint_id"]] = item
                    return self._endpoints_cache
            except Exception:
                pass
        return self._endpoints_cache

    async def update_endpoint_status(self, endpoint_id: str, status: str) -> Optional[Dict[str, Any]]:
        if endpoint_id in self._endpoints_cache:
            self._endpoints_cache[endpoint_id]["status"] = status
            db = mongo_manager.get_database()
            if db is not None:
                try:
                    await db.endpoints.update_one({"endpoint_id": endpoint_id}, {"$set": {"status": status}})
                except Exception:
                    pass
            return self._endpoints_cache[endpoint_id]
        return None


endpoint_repository = MongoEndpointRepository()
