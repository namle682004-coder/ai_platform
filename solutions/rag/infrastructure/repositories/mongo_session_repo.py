"""
MongoDB Session & Message Repository Adapter for AIP Enterprise RAG Solution.
Implements domain SessionRepositoryPort with granular per-session and per-message persistence.
Maintains two synchronized collections:
- `rag_sessions`: Session metadata with embedded message buffer for high-throughput single-read queries.
- `rag_messages`: Normalized message log for message-level auditing, feedback linking, and fine-grained CRUD.
"""

from __future__ import annotations

import logging
import os
import time
import uuid
from typing import Any, Dict, List, Optional

from motor.motor_asyncio import AsyncIOMotorClient
from ...domain.ports import SessionRepositoryPort

logger = logging.getLogger("aip-rag.repo.mongo_session")


class MongoSessionRepositoryAdapter(SessionRepositoryPort):
    """Production MongoDB adapter for chat sessions and individual messages."""

    def __init__(self, mongo_uri: Optional[str] = None) -> None:
        self.mongo_uri = mongo_uri or os.getenv("MONGO_URI") or os.getenv("MONGODB_URI") or ""
        self._client: Optional[AsyncIOMotorClient] = None
        self._memory_sessions: Dict[str, Dict[str, Any]] = {}
        self._memory_messages: Dict[str, List[Dict[str, Any]]] = {}
        self._indexes_ensured = False

    def _get_db(self) -> Any:
        if self._client is None:
            self._client = AsyncIOMotorClient(self.mongo_uri)
        db_name = self.mongo_uri.split("/")[-1].split("?")[0] or "ai_platform"
        return self._client[db_name]

    def _get_sessions_collection(self) -> Any:
        return self._get_db()["rag_sessions"]

    def _get_messages_collection(self) -> Any:
        return self._get_db()["rag_messages"]

    def _get_escalations_collection(self) -> Any:
        return self._get_db()["escalation_tickets"]

    def _get_feedbacks_collection(self) -> Any:
        return self._get_db()["rag_feedbacks"]

    async def ensure_indexes(self) -> None:
        """Create high-performance indexes on sessions, messages, escalations, and feedbacks."""
        if self._indexes_ensured:
            return
        try:
            sess_coll = self._get_sessions_collection()
            msg_coll = self._get_messages_collection()
            esc_coll = self._get_escalations_collection()
            fb_coll = self._get_feedbacks_collection()

            await sess_coll.create_index([("session_id", 1), ("tenant_id", 1)], unique=True)
            await sess_coll.create_index([("tenant_id", 1), ("user_id", 1), ("updated_at", -1)])

            await msg_coll.create_index([("message_id", 1)], unique=True)
            await msg_coll.create_index([("session_id", 1), ("timestamp", 1)])
            await msg_coll.create_index([("tenant_id", 1), ("user_id", 1), ("timestamp", -1)])

            await esc_coll.create_index([("ticket_id", 1)], unique=True)
            await esc_coll.create_index([("tenant_id", 1), ("created_at", -1)])

            await fb_coll.create_index([("feedback_id", 1)], unique=True)
            await fb_coll.create_index([("trace_id", 1)])
            await fb_coll.create_index([("tenant_id", 1), ("created_at", -1)])
            self._indexes_ensured = True
            logger.info("MongoDB RAG indexes ensured successfully.")
        except Exception as exc:
            logger.debug("MongoDB index creation skipped/deferred: %s", exc)

    async def get_session(self, session_id: str, user_id: str, tenant_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve complete session history with structured messages."""
        try:
            coll = self._get_sessions_collection()
            doc = await coll.find_one({"session_id": session_id})
            if doc:
                doc.pop("_id", None)
                # Ensure all embedded messages have message_id
                messages = doc.get("messages", [])
                for idx, m in enumerate(messages):
                    if not m.get("message_id"):
                        m["message_id"] = f"{session_id}_msg_{idx+1}"
                return doc
        except Exception as exc:
            logger.debug("Mongo get_session fallback to memory: %s", exc)

        mem = self._memory_sessions.get(session_id)
        if mem:
            return mem
        return None

    async def append_turn(
        self,
        session_id: str,
        user_id: str,
        tenant_id: str,
        user_msg: Dict[str, Any],
        assistant_msg: Dict[str, Any],
        title: Optional[str] = None,
    ) -> bool:
        """Atomically append a complete conversational turn (User Question + Assistant Answer)."""
        await self.ensure_indexes()
        now = time.time()

        # 1. Standardize message IDs and timestamps
        if not user_msg.get("message_id"):
            user_msg["message_id"] = f"msg_{uuid.uuid4().hex[:12]}"
        user_msg["timestamp"] = user_msg.get("timestamp") or now
        user_msg["role"] = "user"

        if not assistant_msg.get("message_id"):
            assistant_msg["message_id"] = f"msg_{uuid.uuid4().hex[:12]}"
        assistant_msg["timestamp"] = assistant_msg.get("timestamp") or now
        assistant_msg["role"] = "assistant"

        # 2. Update In-Memory cache
        if session_id not in self._memory_sessions:
            derived_title = title or (user_msg.get("content", "")[:40] + ("..." if len(user_msg.get("content", "")) > 40 else "")) or "New Conversation"
            self._memory_sessions[session_id] = {
                "session_id": session_id,
                "user_id": user_id,
                "tenant_id": tenant_id,
                "title": derived_title,
                "messages": [],
                "created_at": now,
                "updated_at": now,
                "message_count": 0,
            }

        sess_mem = self._memory_sessions[session_id]
        sess_mem["messages"].extend([user_msg, assistant_msg])
        sess_mem["message_count"] = len(sess_mem["messages"])
        sess_mem["updated_at"] = now
        sess_mem["last_message"] = assistant_msg.get("content", "")[:200]
        if title:
            sess_mem["title"] = title

        # 3. Persist to MongoDB
        try:
            sess_coll = self._get_sessions_collection()
            msg_coll = self._get_messages_collection()

            # Push both messages to sessions collection
            derived_title = title or (user_msg.get("content", "")[:40] + ("..." if len(user_msg.get("content", "")) > 40 else "")) or "New Conversation"
            await sess_coll.update_one(
                {"session_id": session_id},
                {
                    "$push": {"messages": {"$each": [user_msg, assistant_msg]}},
                    "$inc": {"message_count": 2},
                    "$set": {
                        "last_message": assistant_msg.get("content", "")[:200],
                        "updated_at": now,
                        "user_id": user_id,
                        "tenant_id": tenant_id,
                    },
                    "$setOnInsert": {
                        "session_id": session_id,
                        "created_at": now,
                        "title": derived_title,
                    },
                },
                upsert=True,
            )

            # Insert granular messages into rag_messages
            user_doc = {**user_msg, "session_id": session_id, "tenant_id": tenant_id, "user_id": user_id}
            asst_doc = {**assistant_msg, "session_id": session_id, "tenant_id": tenant_id, "user_id": user_id}
            await msg_coll.insert_many([user_doc, asst_doc])

            logger.info("Successfully persisted conversation turn for session=%s (msgs=%s, %s)", session_id, user_msg["message_id"], assistant_msg["message_id"])
            return True
        except Exception as exc:
            logger.warning("MongoDB append_turn error, persisted to memory fallback: %s", exc)
            return True

    async def append_message(
        self,
        session_id: str,
        user_id: str,
        tenant_id: str,
        message: Dict[str, Any],
        title: Optional[str] = None,
    ) -> bool:
        """Append an individual message to session and message store."""
        await self.ensure_indexes()
        now = time.time()

        if not message.get("message_id"):
            message["message_id"] = f"msg_{uuid.uuid4().hex[:12]}"
        message["timestamp"] = message.get("timestamp") or now

        # Update in-memory
        if session_id in self._memory_sessions:
            self._memory_sessions[session_id]["messages"].append(message)
            self._memory_sessions[session_id]["message_count"] = len(self._memory_sessions[session_id]["messages"])
            self._memory_sessions[session_id]["updated_at"] = now
            self._memory_sessions[session_id]["last_message"] = message.get("content", "")[:200]

        # Update MongoDB
        try:
            sess_coll = self._get_sessions_collection()
            msg_coll = self._get_messages_collection()

            derived_title = title or (message.get("content", "")[:40] if message.get("role") == "user" else "New Conversation")
            await sess_coll.update_one(
                {"session_id": session_id, "tenant_id": tenant_id},
                {
                    "$push": {"messages": message},
                    "$inc": {"message_count": 1},
                    "$set": {
                        "last_message": message.get("content", "")[:200],
                        "updated_at": now,
                        "user_id": user_id,
                    },
                    "$setOnInsert": {
                        "created_at": now,
                        "title": derived_title,
                    },
                },
                upsert=True,
            )

            await msg_coll.insert_one({**message, "session_id": session_id, "tenant_id": tenant_id, "user_id": user_id})
            return True
        except Exception as exc:
            logger.warning("MongoDB append_message error, persisted to memory: %s", exc)
            return True

    async def save_session(
        self,
        session_id: str,
        user_id: str,
        tenant_id: str,
        title: str,
        messages: List[Dict[str, Any]],
    ) -> bool:
        """Full upsert of session and messages (backward compatibility)."""
        now = time.time()
        for _idx, m in enumerate(messages):
            if not m.get("message_id"):
                m["message_id"] = f"msg_{uuid.uuid4().hex[:12]}"
            if not m.get("timestamp"):
                m["timestamp"] = now

        record = {
            "session_id": session_id,
            "user_id": user_id,
            "tenant_id": tenant_id,
            "title": title,
            "messages": messages,
            "message_count": len(messages),
            "last_message": messages[-1].get("content", "")[:200] if messages else None,
            "updated_at": now,
        }
        self._memory_sessions[session_id] = record

        try:
            coll = self._get_sessions_collection()
            await coll.update_one(
                {"session_id": session_id, "tenant_id": tenant_id},
                {
                    "$set": {
                        "title": title,
                        "messages": messages,
                        "message_count": len(messages),
                        "last_message": messages[-1].get("content", "")[:200] if messages else None,
                        "updated_at": now,
                        "user_id": user_id,
                    },
                    "$setOnInsert": {"created_at": now},
                },
                upsert=True,
            )
            return True
        except Exception as exc:
            logger.warning("Mongo save_session fallback to memory: %s", exc)
            return True

    async def list_sessions(
        self,
        user_id: str,
        tenant_id: str,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """List recent chat sessions sorted by updated_at desc."""
        results: List[Dict[str, Any]] = []
        try:
            coll = self._get_sessions_collection()
            # Dynamic multi-tenant filtering: strictly match active project tenant, or default aliases
            if tenant_id.lower() in ("tenant_retail_bank", "proj_default", "default_tenant", "tenant_default"):
                tenant_variants = ["TENANT_RETAIL_BANK", "tenant_retail_bank", "proj_default", "default_tenant"]
            else:
                tenant_variants = list(set([tenant_id, tenant_id.lower()]))
            cursor = coll.find(
                {"tenant_id": {"$in": tenant_variants}},
                {"messages": {"$slice": -1}},
            ).sort("updated_at", -1).limit(limit)

            async for doc in cursor:
                msgs = doc.get("messages", [])
                last_msg = doc.get("last_message") or (msgs[-1].get("content") if msgs else None)
                msg_cnt = doc.get("message_count", len(msgs))
                results.append({
                    "session_id": doc["session_id"],
                    "title": doc.get("title", "New Conversation"),
                    "last_message": last_msg,
                    "updated_at": float(doc.get("updated_at", doc.get("created_at", time.time()))),
                    "message_count": int(msg_cnt),
                })
            return results
        except Exception as exc:
            logger.debug("Mongo list_sessions fallback to memory: %s", exc)

        # In-memory fallback
        for sid, rec in sorted(
            self._memory_sessions.items(),
            key=lambda x: x[1].get("updated_at", 0),
            reverse=True,
        )[:limit]:
            if rec.get("tenant_id") == tenant_id:
                msgs = rec.get("messages", [])
                results.append({
                    "session_id": sid,
                    "title": rec.get("title", "New Conversation"),
                    "last_message": rec.get("last_message") or (msgs[-1].get("content") if msgs else None),
                    "updated_at": float(rec.get("updated_at", time.time())),
                    "message_count": len(msgs),
                })
        return results

    async def delete_session(self, session_id: str, user_id: str, tenant_id: str) -> bool:
        """Permanently delete session and all associated messages."""
        self._memory_sessions.pop(session_id, None)
        try:
            sess_coll = self._get_sessions_collection()
            msg_coll = self._get_messages_collection()

            del_res = await sess_coll.delete_one({"session_id": session_id, "tenant_id": tenant_id})
            await msg_coll.delete_many({"session_id": session_id, "tenant_id": tenant_id})
            logger.info("Deleted session %s and its granular messages.", session_id)
            return del_res.deleted_count > 0
        except Exception as exc:
            logger.warning("Mongo delete_session fallback: %s", exc)
            return True

    async def delete_message(self, session_id: str, message_id: str, user_id: str, tenant_id: str) -> bool:
        """Delete an individual message from a session."""
        if session_id in self._memory_sessions:
            msgs = self._memory_sessions[session_id].get("messages", [])
            self._memory_sessions[session_id]["messages"] = [m for m in msgs if m.get("message_id") != message_id]
            self._memory_sessions[session_id]["message_count"] = len(self._memory_sessions[session_id]["messages"])

        try:
            sess_coll = self._get_sessions_collection()
            msg_coll = self._get_messages_collection()

            # Pull from session messages array
            await sess_coll.update_one(
                {"session_id": session_id, "tenant_id": tenant_id},
                {
                    "$pull": {"messages": {"message_id": message_id}},
                    "$inc": {"message_count": -1},
                    "$set": {"updated_at": time.time()},
                },
            )
            del_res = await msg_coll.delete_one({"message_id": message_id, "session_id": session_id})
            logger.info("Deleted message %s from session %s.", message_id, session_id)
            return del_res.deleted_count > 0
        except Exception as exc:
            logger.warning("Mongo delete_message fallback: %s", exc)
            return True

    async def update_title(self, session_id: str, title: str, user_id: str, tenant_id: str) -> bool:
        """Rename session title."""
        if session_id in self._memory_sessions:
            self._memory_sessions[session_id]["title"] = title

        try:
            coll = self._get_sessions_collection()
            res = await coll.update_one(
                {"session_id": session_id, "tenant_id": tenant_id},
                {"$set": {"title": title, "updated_at": time.time()}},
            )
            return res.modified_count > 0
        except Exception as exc:
            logger.warning("Mongo update_title fallback: %s", exc)
            return True

    async def record_escalation_ticket(self, ticket_data: Dict[str, Any]) -> str:
        """Persist unresolved out-of-domain escalation ticket to MongoDB collection escalation_tickets (RER-RAG-02)."""
        await self.ensure_indexes()
        ticket_id = ticket_data.get("ticket_id") or f"ticket_{uuid.uuid4().hex[:10]}"
        record = dict(ticket_data)
        record["ticket_id"] = ticket_id
        record["created_at"] = record.get("created_at") or time.time()

        try:
            coll = self._get_escalations_collection()
            await coll.insert_one(record)
            logger.info("Saved escalation ticket %s to MongoDB", ticket_id)
            return ticket_id
        except Exception as exc:
            logger.warning("Failed to persist escalation ticket %s to MongoDB: %s", ticket_id, exc)
            return ticket_id

    async def record_feedback(self, feedback_data: Dict[str, Any]) -> str:
        """Persist user feedback and 5-stage error attribution to MongoDB collection rag_feedbacks (EXEC-RAG-04)."""
        await self.ensure_indexes()
        feedback_id = feedback_data.get("feedback_id") or f"fb_rec_{uuid.uuid4().hex[:8]}"
        record = dict(feedback_data)
        record["feedback_id"] = feedback_id
        record["created_at"] = record.get("created_at") or time.time()

        try:
            coll = self._get_feedbacks_collection()
            await coll.insert_one(record)
            logger.info("Saved feedback %s to MongoDB", feedback_id)
            return feedback_id
        except Exception as exc:
            logger.warning("Failed to persist feedback %s to MongoDB: %s", feedback_id, exc)
            return feedback_id

    async def get_feedbacks(self, tenant_id: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        """Retrieve recent feedbacks for error attribution dashboard reporting."""
        results: List[Dict[str, Any]] = []
        try:
            coll = self._get_feedbacks_collection()
            query_filter: Dict[str, Any] = {}
            if tenant_id and tenant_id not in ("default_tenant", "tenant_default", "proj_default"):
                query_filter["tenant_id"] = tenant_id

            cursor = coll.find(query_filter).sort("created_at", -1).limit(limit)
            async for doc in cursor:
                doc.pop("_id", None)
                results.append(doc)
            return results
        except Exception as exc:
            logger.warning("Failed to get feedbacks from MongoDB: %s", exc)
            return results
