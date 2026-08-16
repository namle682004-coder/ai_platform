from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from common.interfaces.projects import IProjectRepository
from common.database.mongodb import mongo_manager

class MongoProjectRepository(IProjectRepository):
    """MongoDB Atlas implementation for User Projects."""

    async def create_project(self, project_record: Dict[str, Any]) -> Dict[str, Any]:
        db = mongo_manager.get_database()
        if db is not None:
            try:
                await db.projects.insert_one(dict(project_record))
            except Exception:
                pass
        project_record.pop("_id", None)
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
                    return projs
            except Exception:
                pass
        return []

    async def get_project(self, project_id: str) -> Optional[Dict[str, Any]]:
        db = mongo_manager.get_database()
        if db is not None:
            try:
                doc = await db.projects.find_one({"project_id": project_id}, {"_id": 0})
                if doc:
                    doc.pop("_id", None)
                    return doc
            except Exception:
                pass
        return None

project_repository = MongoProjectRepository()
