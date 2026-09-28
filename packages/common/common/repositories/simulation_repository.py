"""
Concrete MongoDB Atlas Repositories for User Simulation & Interactive Playground Data.
Compliant with Clean Architecture DDD.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from common.database.mongodb import mongo_manager
from common.interfaces.simulations import (
    ISimulationRunRepository,
    IChatSessionRepository,
    IOCRRecordRepository,
    IEKYCSessionRepository,
    IAudioRecordRepository,
)


class MongoSimulationRunRepository(ISimulationRunRepository):
    """MongoDB implementation for general simulation experiment runs."""

    def __init__(self):
        self._memory_cache: Dict[str, Dict[str, Any]] = {}

    async def create_run(self, run_record: Dict[str, Any]) -> Dict[str, Any]:
        db = mongo_manager.get_database()
        if db is not None:
            try:
                await db.simulation_runs.insert_one(dict(run_record))
            except Exception:
                pass
        run_record.pop("_id", None)
        self._memory_cache[run_record["run_id"]] = run_record
        return run_record

    async def get_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        db = mongo_manager.get_database()
        if db is not None:
            try:
                doc = await db.simulation_runs.find_one({"run_id": run_id}, {"_id": 0})
                if doc:
                    return doc
            except Exception:
                pass
        return self._memory_cache.get(run_id)

    async def list_runs(
        self,
        user_id: Optional[str] = None,
        domain: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
        skip: int = 0,
    ) -> List[Dict[str, Any]]:
        db = mongo_manager.get_database()
        query: Dict[str, Any] = {}
        if user_id:
            query["user_id"] = user_id
        if domain:
            query["domain"] = domain
        if status:
            query["status"] = status

        if db is not None:
            try:
                cursor = db.simulation_runs.find(query, {"_id": 0}).sort("created_at", -1).skip(skip).limit(limit)
                docs = await cursor.to_list(length=limit)
                if docs:
                    return docs
            except Exception:
                pass

        results = list(self._memory_cache.values())
        if user_id:
            results = [r for r in results if r.get("user_id") == user_id]
        if domain:
            results = [r for r in results if r.get("domain") == domain]
        if status:
            results = [r for r in results if r.get("status") == status]
        return results[skip : skip + limit]

    async def delete_run(self, run_id: str) -> bool:
        db = mongo_manager.get_database()
        if db is not None:
            try:
                res = await db.simulation_runs.delete_one({"run_id": run_id})
                if res.deleted_count > 0:
                    self._memory_cache.pop(run_id, None)
                    return True
            except Exception:
                pass
        return self._memory_cache.pop(run_id, None) is not None


class MongoChatSessionRepository(IChatSessionRepository):
    """MongoDB implementation for multi-turn chat sessions and message threads."""

    def __init__(self):
        self._sessions_cache: Dict[str, Dict[str, Any]] = {}
        self._messages_cache: Dict[str, List[Dict[str, Any]]] = {}
        self._templates_cache: Dict[str, Dict[str, Any]] = {}

    async def create_session(self, session_data: Dict[str, Any]) -> Dict[str, Any]:
        db = mongo_manager.get_database()
        if db is not None:
            try:
                await db.chat_sessions.insert_one(dict(session_data))
            except Exception:
                pass
        session_data.pop("_id", None)
        self._sessions_cache[session_data["session_id"]] = session_data
        self._messages_cache[session_data["session_id"]] = []
        return session_data

    async def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        db = mongo_manager.get_database()
        if db is not None:
            try:
                doc = await db.chat_sessions.find_one({"session_id": session_id}, {"_id": 0})
                if doc:
                    return doc
            except Exception:
                pass
        return self._sessions_cache.get(session_id)

    async def list_sessions(self, user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        db = mongo_manager.get_database()
        if db is not None:
            try:
                cursor = db.chat_sessions.find({"user_id": user_id}, {"_id": 0}).sort("updated_at", -1).limit(limit)
                docs = await cursor.to_list(length=limit)
                if docs:
                    return docs
            except Exception:
                pass
        return [s for s in self._sessions_cache.values() if s.get("user_id") == user_id][:limit]

    async def add_message(self, message_data: Dict[str, Any]) -> Dict[str, Any]:
        db = mongo_manager.get_database()
        session_id = message_data["session_id"]
        if db is not None:
            try:
                await db.chat_messages.insert_one(dict(message_data))
                await db.chat_sessions.update_one(
                    {"session_id": session_id},
                    {"$inc": {"message_count": 1}, "$set": {"updated_at": message_data.get("created_at")}}
                )
            except Exception:
                pass
        message_data.pop("_id", None)
        if session_id not in self._messages_cache:
            self._messages_cache[session_id] = []
        self._messages_cache[session_id].append(message_data)
        if session_id in self._sessions_cache:
            self._sessions_cache[session_id]["message_count"] = len(self._messages_cache[session_id])
        return message_data

    async def get_session_messages(self, session_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        db = mongo_manager.get_database()
        if db is not None:
            try:
                cursor = db.chat_messages.find({"session_id": session_id}, {"_id": 0}).sort("created_at", 1).limit(limit)
                docs = await cursor.to_list(length=limit)
                if docs:
                    return docs
            except Exception:
                pass
        return self._messages_cache.get(session_id, [])[:limit]

    async def delete_session(self, session_id: str) -> bool:
        db = mongo_manager.get_database()
        if db is not None:
            try:
                await db.chat_sessions.delete_one({"session_id": session_id})
                await db.chat_messages.delete_many({"session_id": session_id})
            except Exception:
                pass
        self._sessions_cache.pop(session_id, None)
        self._messages_cache.pop(session_id, None)
        return True

    async def create_prompt_template(self, template_data: Dict[str, Any]) -> Dict[str, Any]:
        db = mongo_manager.get_database()
        if db is not None:
            try:
                await db.prompt_templates.insert_one(dict(template_data))
            except Exception:
                pass
        template_data.pop("_id", None)
        self._templates_cache[template_data["template_id"]] = template_data
        return template_data

    async def list_prompt_templates(self, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        db = mongo_manager.get_database()
        query = {"$or": [{"is_public": True}, {"user_id": user_id}]} if user_id else {}
        if db is not None:
            try:
                cursor = db.prompt_templates.find(query, {"_id": 0}).sort("created_at", -1)
                docs = await cursor.to_list(length=100)
                if docs:
                    return docs
            except Exception:
                pass
        return list(self._templates_cache.values())


class MongoOCRRecordRepository(IOCRRecordRepository):
    """MongoDB implementation for OCR document extractions."""

    def __init__(self):
        self._records_cache: Dict[str, Dict[str, Any]] = {}

    async def create_record(self, record_data: Dict[str, Any]) -> Dict[str, Any]:
        db = mongo_manager.get_database()
        if db is not None:
            try:
                await db.ocr_records.insert_one(dict(record_data))
            except Exception:
                pass
        record_data.pop("_id", None)
        self._records_cache[record_data["record_id"]] = record_data
        return record_data

    async def get_record(self, record_id: str) -> Optional[Dict[str, Any]]:
        db = mongo_manager.get_database()
        if db is not None:
            try:
                doc = await db.ocr_records.find_one({"record_id": record_id}, {"_id": 0})
                if doc:
                    return doc
            except Exception:
                pass
        return self._records_cache.get(record_id)

    async def list_records(
        self, user_id: Optional[str] = None, doc_type: Optional[str] = None, limit: int = 50
    ) -> List[Dict[str, Any]]:
        db = mongo_manager.get_database()
        query: Dict[str, Any] = {}
        if user_id:
            query["user_id"] = user_id
        if doc_type:
            query["doc_type"] = doc_type

        if db is not None:
            try:
                cursor = db.ocr_records.find(query, {"_id": 0}).sort("created_at", -1).limit(limit)
                docs = await cursor.to_list(length=limit)
                if docs:
                    return docs
            except Exception:
                pass
        results = list(self._records_cache.values())
        if user_id:
            results = [r for r in results if r.get("user_id") == user_id]
        if doc_type:
            results = [r for r in results if r.get("doc_type") == doc_type]
        return results[:limit]


class MongoEKYCSessionRepository(IEKYCSessionRepository):
    """MongoDB implementation for eKYC biometric verification sessions."""

    def __init__(self):
        self._sessions_cache: Dict[str, Dict[str, Any]] = {}

    async def create_session(self, session_data: Dict[str, Any]) -> Dict[str, Any]:
        db = mongo_manager.get_database()
        if db is not None:
            try:
                await db.ekyc_sessions.insert_one(dict(session_data))
            except Exception:
                pass
        session_data.pop("_id", None)
        self._sessions_cache[session_data["session_id"]] = session_data
        return session_data

    async def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        db = mongo_manager.get_database()
        if db is not None:
            try:
                doc = await db.ekyc_sessions.find_one({"session_id": session_id}, {"_id": 0})
                if doc:
                    return doc
            except Exception:
                pass
        return self._sessions_cache.get(session_id)

    async def list_sessions(self, user_id: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        db = mongo_manager.get_database()
        query = {"user_id": user_id} if user_id else {}
        if db is not None:
            try:
                cursor = db.ekyc_sessions.find(query, {"_id": 0}).sort("verified_at", -1).limit(limit)
                docs = await cursor.to_list(length=limit)
                if docs:
                    return docs
            except Exception:
                pass
        results = list(self._sessions_cache.values())
        if user_id:
            results = [s for s in results if s.get("user_id") == user_id]
        return results[:limit]


class MongoAudioRecordRepository(IAudioRecordRepository):
    """MongoDB implementation for Speech-to-Text and Text-to-Speech simulation records."""

    def __init__(self):
        self._stt_cache: Dict[str, Dict[str, Any]] = {}
        self._tts_cache: Dict[str, Dict[str, Any]] = {}

    async def create_transcription(self, data: Dict[str, Any]) -> Dict[str, Any]:
        db = mongo_manager.get_database()
        if db is not None:
            try:
                await db.stt_records.insert_one(dict(data))
            except Exception:
                pass
        data.pop("_id", None)
        self._stt_cache[data["record_id"]] = data
        return data

    async def list_transcriptions(self, user_id: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        db = mongo_manager.get_database()
        query = {"user_id": user_id} if user_id else {}
        if db is not None:
            try:
                cursor = db.stt_records.find(query, {"_id": 0}).sort("created_at", -1).limit(limit)
                docs = await cursor.to_list(length=limit)
                if docs:
                    return docs
            except Exception:
                pass
        results = list(self._stt_cache.values())
        if user_id:
            results = [r for r in results if r.get("user_id") == user_id]
        return results[:limit]

    async def create_synthesis(self, data: Dict[str, Any]) -> Dict[str, Any]:
        db = mongo_manager.get_database()
        if db is not None:
            try:
                await db.tts_records.insert_one(dict(data))
            except Exception:
                pass
        data.pop("_id", None)
        self._tts_cache[data["record_id"]] = data
        return data

    async def list_syntheses(self, user_id: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        db = mongo_manager.get_database()
        query = {"user_id": user_id} if user_id else {}
        if db is not None:
            try:
                cursor = db.tts_records.find(query, {"_id": 0}).sort("created_at", -1).limit(limit)
                docs = await cursor.to_list(length=limit)
                if docs:
                    return docs
            except Exception:
                pass
        results = list(self._tts_cache.values())
        if user_id:
            results = [r for r in results if r.get("user_id") == user_id]
        return results[:limit]


# Global Singletons
simulation_run_repository = MongoSimulationRunRepository()
chat_session_repository = MongoChatSessionRepository()
ocr_record_repository = MongoOCRRecordRepository()
ekyc_session_repository = MongoEKYCSessionRepository()
audio_record_repository = MongoAudioRecordRepository()
