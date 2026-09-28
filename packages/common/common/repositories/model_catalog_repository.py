from typing import Optional, Dict, Any, List
from common.interfaces.models import IModelCatalogRepository
from common.database.mongodb import mongo_manager

DEFAULT_MODELS = [
    {
        "model_id": "deepseek-v3",
        "name": "DeepSeek V3 671B",
        "provider": "vllm_local",
        "context_window": 64000,
        "input_price_per_1k": 0.0005,
        "output_price_per_1k": 0.0015,
        "status": "active",
    },
    {
        "model_id": "phowhisper-large-v3",
        "name": "PhoWhisper ASR Large v3",
        "provider": "triton_local",
        "context_window": 16000,
        "input_price_per_1k": 0.0002,
        "output_price_per_1k": 0.0002,
        "status": "active",
    },
]


class MongoModelCatalogRepository(IModelCatalogRepository):
    """MongoDB Atlas implementation for Model Catalog Metadata."""

    def __init__(self):
        self._models_cache: Dict[str, Dict[str, Any]] = {
            m["model_id"]: dict(m) for m in DEFAULT_MODELS
        }

    async def register_model(self, model_record: Dict[str, Any]) -> Dict[str, Any]:
        db = mongo_manager.get_database()
        if db is not None:
            try:
                await db.models.insert_one(dict(model_record))
            except Exception:
                pass
        model_record.pop("_id", None)
        self._models_cache[model_record["model_id"]] = model_record
        return model_record

    async def get_model(self, model_id: str) -> Optional[Dict[str, Any]]:
        if model_id in self._models_cache:
            return dict(self._models_cache[model_id])
        db = mongo_manager.get_database()
        if db is not None:
            try:
                doc = await db.models.find_one({"model_id": model_id}, {"_id": 0})
                if doc:
                    doc.pop("_id", None)
                    return doc
            except Exception:
                pass
        return None

    async def list_models(self) -> List[Dict[str, Any]]:
        db = mongo_manager.get_database()
        if db is not None:
            try:
                cursor = db.models.find({}, {"_id": 0})
                models = await cursor.to_list(length=100)
                if models:
                    for m in models:
                        m.pop("_id", None)
                    return models
            except Exception:
                pass
        return [dict(m) for m in self._models_cache.values()]


model_catalog_repository = MongoModelCatalogRepository()
