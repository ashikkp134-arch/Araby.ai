"""File and folder schemas."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class FolderCreateRequest(BaseModel):
    """Payload for creating a folder.

    Attributes:
        name: Folder name.
        parent_path: Parent folder path (empty for root).
    """

    name: str = Field(min_length=1, max_length=120)
    parent_path: str = Field(default="")


class FolderResponse(BaseModel):
    """Folder representation.

    Attributes:
        id: Folder identifier.
        project_id: Parent project id.
        name: Folder name.
        path: Full folder path.
        parent_id: Parent folder id if any.
        created_at: Creation timestamp.
    """

    id: str
    project_id: str
    name: str
    path: str
    parent_id: Optional[str] = None
    created_at: datetime


class FileCreateRequest(BaseModel):
    """Payload for creating a file.

    Attributes:
        name: File name including extension.
        folder_path: Parent folder path.
        content: Initial file content.
    """

    name: str = Field(min_length=1, max_length=255)
    folder_path: str = Field(default="")
    content: str = Field(default="")


class FileUpdateRequest(BaseModel):
    """Payload for updating file content or name.

    Attributes:
        content: Optional new content.
        name: Optional new file name.
    """

    content: Optional[str] = None
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)


class FileResponse(BaseModel):
    """File representation.

    Attributes:
        id: File identifier.
        project_id: Parent project id.
        name: File name.
        path: Full file path.
        folder_id: Parent folder id if any.
        content: File content.
        language: Detected language hint.
        updated_at: Last update timestamp.
        created_at: Creation timestamp.
    """

    id: str
    project_id: str
    name: str
    path: str
    folder_id: Optional[str] = None
    content: str
    language: str
    updated_at: datetime
    created_at: datetime


class FileTreeNode(BaseModel):
    """Recursive file tree node.

    Attributes:
        id: Node identifier.
        name: Node name.
        path: Full path.
        type: Either 'file' or 'folder'.
        language: Language for files.
        children: Nested children for folders.
    """

    id: str
    name: str
    path: str
    type: str
    language: Optional[str] = None
    children: Optional[List["FileTreeNode"]] = None


FileTreeNode.model_rebuild()
