from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from common.interfaces.sessions import ISessionRepository
from common.database.mongodb import mongo_manager


class MongoSessionRepository(ISessionRepository):
    """MongoDB Atlas implementation for Active User Sessions & Tokens."""

    def __init__(self):
        self._sessions_cache: Dict[str, Dict[str, Any]] = {}

    async def create_session(self, session_record: Dict[str, Any]) -> Dict[str, Any]:
        if "created_at" not in session_record:
            session_record["created_at"] = datetime.now(timezone.utc).isoformat()
        db = mongo_manager.get_database()
        if db is not None:
            try:
                await db.sessions.insert_one(dict(session_record))
            except Exception:
                pass
        session_record.pop("_id", None)
        self._sessions_cache[session_record["session_id"]] = session_record
        return session_record

    async def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        if session_id in self._sessions_cache:
            return dict(self._sessions_cache[session_id])
        db = mongo_manager.get_database()
        if db is not None:
            try:
                doc = await db.sessions.find_one({"session_id": session_id}, {"_id": 0})
                if doc:
                    doc.pop("_id", None)
                    return doc
            except Exception:
                pass
        return None

    async def list_user_sessions(self, user_id: str) -> List[Dict[str, Any]]:
        db = mongo_manager.get_database()
        if db is not None:
            try:
                cursor = db.sessions.find({"user_id": user_id}, {"_id": 0})
                sessions = await cursor.to_list(length=100)
                if sessions:
                    for s in sessions:
                        s.pop("_id", None)
                    return sessions
            except Exception:
                pass
        return [dict(s) for s in self._sessions_cache.values() if s.get("user_id") == user_id]

    async def revoke_session(self, session_id: str) -> bool:
        if session_id in self._sessions_cache:
            del self._sessions_cache[session_id]
            db = mongo_manager.get_database()
            if db is not None:
                try:
                    await db.sessions.delete_one({"session_id": session_id})
                except Exception:
                    pass
            return True
        return False


session_repository = MongoSessionRepository()
