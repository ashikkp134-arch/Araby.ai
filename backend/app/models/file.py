"""File and folder document model helpers."""

from typing import Any, Dict, Optional

from app.models.base import utc_now


def build_folder_document(
    project_id: Any,
    name: str,
    path: str,
    parent_id: Optional[Any] = None,
) -> Dict[str, Any]:
    """Build a folder document.

    Args:
        project_id: Parent project ObjectId.
        name: Folder name.
        path: Full folder path.
        parent_id: Optional parent folder ObjectId.

    Returns:
        MongoDB-ready folder document.
    """
    now = utc_now()
    return {
        "project_id": project_id,
        "name": name,
        "path": path,
        "parent_id": parent_id,
        "created_at": now,
        "updated_at": now,
    }


def build_file_document(
    project_id: Any,
    name: str,
    path: str,
    content: str,
    language: str,
    folder_id: Optional[Any] = None,
) -> Dict[str, Any]:
    """Build a file document.

    Args:
        project_id: Parent project ObjectId.
        name: File name.
        path: Full file path.
        content: File content.
        language: Language identifier.
        folder_id: Optional parent folder ObjectId.

    Returns:
        MongoDB-ready file document.
    """
    now = utc_now()
    return {
        "project_id": project_id,
        "name": name,
        "path": path,
        "content": content,
        "language": language,
        "folder_id": folder_id,
        "created_at": now,
        "updated_at": now,
    }
