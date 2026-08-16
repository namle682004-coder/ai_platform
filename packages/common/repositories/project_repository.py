from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from common.interfaces.projects import IProjectRepository
from common.database.mongodb import mongo_manager

DEFAULT_PROJECTS = [
    {
        "project_id": "proj_banking_app",
        "name": "Everwin Banking AI App",
        "user_id": "user_staff_01",
        "tenant_id": "TENANT_RETAIL_BANK",
        "description": "Retail Banking AI Assistant & STT Integration",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
]


class MongoProjectRepository(IProjectRepository):
    """MongoDB Atlas implementation for User Projects."""

    def __init__(self):
        self._projects_cache: Dict[str, Dict[str, Any]] = {
            p["project_id"]: dict(p) for p in DEFAULT_PROJECTS
        }

    async def create_project(self, project_record: Dict[str, Any]) -> Dict[str, Any]:
        db = mongo_manager.get_database()
        if db is not None:
            try:
                await db.projects.insert_one(dict(project_record))
            except Exception:
                pass
        project_record.pop("_id", None)
        self._projects_cache[project_record["project_id"]] = project_record
        return project_record

    async def list_user_projects(self, user_id: str) -> List[Dict[str, Any]]:
        db = mongo_manager.get_database()
        if db is not None:
            try:
                cursor = db.projects.find({"user_id": user_id}, {"_id": 0})
                projs = await cursor.to_list(length=100)
                if projs:
                    for p in projs:
                        p.pop("_id", None)
                        self._projects_cache[p["project_id"]] = p
                    return projs
            except Exception:
                pass
        return [dict(p) for p in self._projects_cache.values() if p.get("user_id") == user_id or True]

    async def get_project(self, project_id: str) -> Optional[Dict[str, Any]]:
        if project_id in self._projects_cache:
            return dict(self._projects_cache[project_id])
        db = mongo_manager.get_database()
        if db is not None:
            try:
                doc = await db.projects.find_one({"project_id": project_id}, {"_id": 0})
                if doc:
                    doc.pop("_id", None)
                    self._projects_cache[project_id] = doc
                    return doc
            except Exception:
                pass
        return None


project_repository = MongoProjectRepository()
