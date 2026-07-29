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


class DiffLine(BaseModel):
    """One rendered line inside a diff hunk.

    Attributes:
        type: context, add, or remove.
        old_line: 1-based line number before the change (None for additions).
        new_line: 1-based line number after the change (None for removals).
        content: Line text without its trailing newline.
    """

    type: str
    old_line: Optional[int] = None
    new_line: Optional[int] = None
    content: str = ""


class DiffHunk(BaseModel):
    """Contiguous changed region with surrounding context lines.

    Attributes:
        old_start: First 1-based line of the hunk in the old file.
        old_lines: Number of old-file lines covered by the hunk.
        new_start: First 1-based line of the hunk in the new file.
        new_lines: Number of new-file lines covered by the hunk.
        lines: Ordered context/add/remove lines.
    """

    old_start: int = 0
    old_lines: int = 0
    new_start: int = 0
    new_lines: int = 0
    lines: List[DiffLine] = Field(default_factory=list)


class FileChangeDiff(BaseModel):
    """Line-level diff for a single applied file change.

    Attributes:
        additions: Total added lines.
        deletions: Total removed lines.
        is_new_file: Whether the file did not exist before the change.
        is_deleted: Whether the change removed the file.
        truncated: Whether hunks were capped for very large diffs.
        hunks: Rendered diff hunks (empty when truncated or unchanged).
    """

    additions: int = 0
    deletions: int = 0
    is_new_file: bool = False
    is_deleted: bool = False
    truncated: bool = False
    hunks: List[DiffHunk] = Field(default_factory=list)


class FileChangeProposal(BaseModel):
    """Proposed file modification from the AI.

    Attributes:
        path: Target file path.
        action: create, update, or delete.
        content: New content for create/update.
        diff: Line-level diff, attached once the change is applied.
    """

    path: str
    action: str
    content: Optional[str] = None
    diff: Optional[FileChangeDiff] = None


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
        undone: Whether this message's file changes were reverted via undo.
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
    undone: bool = False
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


class UndoChangesResponse(BaseModel):
    """Result of reverting the latest AI-applied change set.

    Attributes:
        message_id: Assistant message whose changes were reverted.
        restored_paths: File paths that were restored or removed.
    """

    message_id: str
    restored_paths: List[str] = Field(default_factory=list)
