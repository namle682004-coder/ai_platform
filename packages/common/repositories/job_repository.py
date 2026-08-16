from typing import Optional, Dict, Any
from common.interfaces.jobs import IJobRepository
from common.database.mongodb import mongo_manager


class MongoJobRepository(IJobRepository):
    """MongoDB Atlas implementation for Async Job Life Cycle."""

    def __init__(self):
        self._jobs_cache: Dict[str, Dict[str, Any]] = {}

    async def create_job(self, job_record: Dict[str, Any]) -> Dict[str, Any]:
        db = mongo_manager.get_database()
        if db is not None:
            try:
                await db.jobs.insert_one(dict(job_record))
            except Exception:
                pass
        job_record.pop("_id", None)
        self._jobs_cache[job_record["job_id"]] = job_record
        return job_record

    async def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        if job_id in self._jobs_cache:
            return self._jobs_cache[job_id]
        db = mongo_manager.get_database()
        if db is not None:
            try:
                doc = await db.jobs.find_one({"job_id": job_id}, {"_id": 0})
                if doc:
                    doc.pop("_id", None)
                    self._jobs_cache[job_id] = doc
                    return doc
            except Exception:
                pass
        return None

    async def update_job_status(self, job_id: str, status: str, updates: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        payload = {"status": status}
        if updates:
            payload.update(updates)

        if job_id in self._jobs_cache:
            self._jobs_cache[job_id].update(payload)
            db = mongo_manager.get_database()
            if db is not None:
                try:
                    await db.jobs.update_one({"job_id": job_id}, {"$set": payload})
                except Exception:
                    pass
            return self._jobs_cache[job_id]
        return None


job_repository = MongoJobRepository()
