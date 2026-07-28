"""Chat schemas."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ChatMessageRequest(BaseModel):
    """User chat message payload.

    Attributes:
        content: User message text.
        current_file_path: Currently open file path.
        selected_code: Optional selected code snippet.
        open_tabs: Paths of open editor tabs.
        apply_changes: Whether AI may modify files.
    """

    content: str = Field(min_length=1, max_length=8000)
    current_file_path: Optional[str] = None
    selected_code: Optional[str] = None
    open_tabs: List[str] = Field(default_factory=list)
    apply_changes: bool = True


class FileChangeProposal(BaseModel):
    """Proposed file modification from the AI.

    Attributes:
        path: Target file path.
        action: create, update, or delete.
        content: New content for create/update.
    """

    path: str
    action: str
    content: Optional[str] = None


class ChatMessageResponse(BaseModel):
    """Persisted chat message.

    Attributes:
        id: Message identifier.
        session_id: Parent session id.
        project_id: Parent project id.
        role: Message role (user/assistant).
        content: Message text.
        token_count: Approximate token usage.
        model: Model used for assistant replies.
        latency_ms: Response latency in milliseconds.
        file_changes: Applied or proposed file changes.
        created_at: Creation timestamp.
    """

    id: str
    session_id: str
    project_id: str
    role: str
    content: str
    token_count: Optional[int] = None
    model: Optional[str] = None
    latency_ms: Optional[int] = None
    file_changes: List[FileChangeProposal] = Field(default_factory=list)
    created_at: datetime


class ChatSessionResponse(BaseModel):
    """Chat session metadata.

    Attributes:
        id: Session identifier.
        project_id: Parent project id.
        created_at: Creation timestamp.
        updated_at: Last update timestamp.
    """

    id: str
    project_id: str
    created_at: datetime
    updated_at: datetime


class ChatCompletionResponse(BaseModel):
    """Full chat turn response.

    Attributes:
        user_message: Persisted user message.
        assistant_message: Persisted assistant message.
        applied_changes: File changes that were applied.
        metadata: Extra telemetry.
    """

    user_message: ChatMessageResponse
    assistant_message: ChatMessageResponse
    applied_changes: List[FileChangeProposal] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
