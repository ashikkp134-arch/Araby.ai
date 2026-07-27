"""Project and workspace schemas."""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class WorkspaceType(str, Enum):
    """Supported workspace environments."""

    JAVASCRIPT = "javascript"
    PYTHON = "python"
    WEBSITE = "website"


class ProjectCreateRequest(BaseModel):
    """Payload for creating a project.

    Attributes:
        name: Project display name.
        description: Optional project description.
        workspace_type: Target workspace type.
    """

    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=500)
    workspace_type: WorkspaceType


class ProjectImportFile(BaseModel):
    """A single file included when importing a local folder.

    Attributes:
        path: Project-relative file path (e.g. src/index.js).
        content: UTF-8 text content.
    """

    path: str = Field(min_length=1, max_length=500)
    content: str = Field(default="", max_length=262_144)


class ProjectImportRequest(BaseModel):
    """Payload for importing a local folder as a project.

    Attributes:
        name: Project display name.
        description: Optional project description.
        workspace_type: Target workspace type.
        files: Text files to seed into the project.
    """

    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=500)
    workspace_type: WorkspaceType
    files: list[ProjectImportFile] = Field(min_length=1, max_length=200)


class ProjectUpdateRequest(BaseModel):
    """Payload for updating a project.

    Attributes:
        name: Optional new name.
        description: Optional new description.
    """

    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    description: Optional[str] = Field(default=None, max_length=500)


class ProjectResponse(BaseModel):
    """Public project representation.

    Attributes:
        id: Project identifier.
        name: Project name.
        description: Project description.
        workspace_type: Workspace type.
        user_id: Owner user id.
        created_at: Creation timestamp.
        updated_at: Last update timestamp.
    """

    id: str
    name: str
    description: str
    workspace_type: WorkspaceType
    user_id: str
    created_at: datetime
    updated_at: datetime


class WorkspaceInfo(BaseModel):
    """Workspace card metadata.

    Attributes:
        type: Workspace type key.
        title: Display title.
        description: Short description.
        language_hint: Primary language label.
    """

    type: WorkspaceType
    title: str
    description: str
    language_hint: str
