"""Chat document model helpers."""

from typing import Any, Dict, List, Optional

from app.models.base import utc_now


def build_chat_session_document(project_id: Any, user_id: Any) -> Dict[str, Any]:
    """Build a chat session document.

    Args:
        project_id: Parent project ObjectId.
        user_id: Owner user ObjectId.

    Returns:
        MongoDB-ready chat session document.
    """
    now = utc_now()
    return {
        "project_id": project_id,
        "user_id": user_id,
        "created_at": now,
        "updated_at": now,
    }


def build_chat_message_document(
    session_id: Any,
    project_id: Any,
    role: str,
    content: str,
    token_count: Optional[int] = None,
    model: Optional[str] = None,
    latency_ms: Optional[int] = None,
    file_changes: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Build a chat message document.

    Args:
        session_id: Parent session ObjectId.
        project_id: Parent project ObjectId.
        role: Message role.
        content: Message content.
        token_count: Optional token usage.
        model: Optional model name.
        latency_ms: Optional latency.
        file_changes: Optional applied file changes.

    Returns:
        MongoDB-ready chat message document.
    """
    return {
        "session_id": session_id,
        "project_id": project_id,
        "role": role,
        "content": content,
        "token_count": token_count,
        "model": model,
        "latency_ms": latency_ms,
        "file_changes": file_changes or [],
        "created_at": utc_now(),
    }
