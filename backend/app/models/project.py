"""Project document model helpers."""

from typing import Any, Dict

from app.models.base import utc_now
from app.schemas.project import WorkspaceType


def build_project_document(
    user_id: Any,
    name: str,
    description: str,
    workspace_type: WorkspaceType,
) -> Dict[str, Any]:
    """Build a new project document for insertion.

    Args:
        user_id: Owner ObjectId.
        name: Project name.
        description: Project description.
        workspace_type: Workspace type enum.

    Returns:
        MongoDB-ready project document.
    """
    now = utc_now()
    return {
        "user_id": user_id,
        "name": name.strip(),
        "description": description.strip(),
        "workspace_type": workspace_type.value,
        "created_at": now,
        "updated_at": now,
    }
