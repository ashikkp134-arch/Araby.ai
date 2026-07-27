"""Chat session and message repositories."""

from typing import Any, Dict, List, Optional, Tuple

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models.base import serialize_doc, utc_now
from app.models.chat import build_chat_message_document, build_chat_session_document


class ChatRepository:
    """Data-access layer for chat sessions and messages."""

    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        """Initialize the repository.

        Args:
            db: MongoDB database handle.
        """
        self._sessions = db.chat_sessions
        self._messages = db.chat_messages

    async def get_or_create_session(
        self,
        project_id: ObjectId,
        user_id: ObjectId,
    ) -> Dict[str, Any]:
        """Return an existing chat session or create one.

        Args:
            project_id: Parent project id.
            user_id: Owner user id.

        Returns:
            Serialized chat session.
        """
        existing = await self._sessions.find_one({"project_id": project_id})
        if existing:
            return serialize_doc(existing)  # type: ignore[return-value]
        doc = build_chat_session_document(project_id, user_id)
        result = await self._sessions.insert_one(doc)
        doc["_id"] = result.inserted_id
        return serialize_doc(doc)  # type: ignore[return-value]

    async def add_message(
        self,
        session_id: ObjectId,
        project_id: ObjectId,
        role: str,
        content: str,
        token_count: Optional[int] = None,
        model: Optional[str] = None,
        latency_ms: Optional[int] = None,
        file_changes: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Persist a chat message and touch the session.

        Args:
            session_id: Parent session id.
            project_id: Parent project id.
            role: Message role.
            content: Message content.
            token_count: Optional token usage.
            model: Optional model name.
            latency_ms: Optional latency.
            file_changes: Optional file change payloads.

        Returns:
            Serialized message document.
        """
        doc = build_chat_message_document(
            session_id=session_id,
            project_id=project_id,
            role=role,
            content=content,
            token_count=token_count,
            model=model,
            latency_ms=latency_ms,
            file_changes=file_changes,
        )
        result = await self._messages.insert_one(doc)
        doc["_id"] = result.inserted_id
        await self._sessions.update_one(
            {"_id": session_id},
            {"$set": {"updated_at": utc_now()}},
        )
        return serialize_doc(doc)  # type: ignore[return-value]

    async def list_messages(
        self,
        session_id: ObjectId,
        skip: int,
        limit: int,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """List messages for a session with pagination.

        Args:
            session_id: Parent session id.
            skip: Documents to skip.
            limit: Max documents to return.

        Returns:
            Tuple of serialized messages and total count.
        """
        query = {"session_id": session_id}
        total = await self._messages.count_documents(query)
        cursor = self._messages.find(query).sort("created_at", 1).skip(skip).limit(limit)
        docs = await cursor.to_list(length=limit)
        return [serialize_doc(doc) for doc in docs], total  # type: ignore[misc]

    async def recent_messages(
        self,
        session_id: ObjectId,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """Fetch the most recent messages for context building.

        Args:
            session_id: Parent session id.
            limit: Max messages to return.

        Returns:
            Serialized messages in chronological order.
        """
        cursor = self._messages.find({"session_id": session_id}).sort("created_at", -1).limit(limit)
        docs = await cursor.to_list(length=limit)
        docs.reverse()
        return [serialize_doc(doc) for doc in docs]  # type: ignore[misc]

    async def delete_for_project(self, project_id: ObjectId) -> None:
        """Delete chat sessions and messages for a project.

        Args:
            project_id: Parent project id.
        """
        await self._messages.delete_many({"project_id": project_id})
        await self._sessions.delete_many({"project_id": project_id})
