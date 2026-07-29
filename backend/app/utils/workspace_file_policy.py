"""Workspace file-type edit policy.

Python and JavaScript workspaces may contain mixed files for viewing, but only
language-specific extensions may be created, updated, deleted, or AI-enhanced.
Website workspaces remain unrestricted for typical web assets.
"""

from __future__ import annotations

from typing import FrozenSet, Optional

from app.utils.exceptions import ValidationAppError

PYTHON_EDITABLE_EXTENSIONS: FrozenSet[str] = frozenset({".py"})
JAVASCRIPT_EDITABLE_EXTENSIONS: FrozenSet[str] = frozenset({".js", ".jsx", ".ts", ".tsx"})

PYTHON_EDIT_MESSAGE = "Only Python files can be edited or enhanced in this workspace."
JAVASCRIPT_EDIT_MESSAGE = (
    "Only JavaScript-related files (.js, .jsx, .ts, .tsx) can be edited or "
    "enhanced in this workspace."
)


def _extension_of(path: str) -> str:
    name = (path or "").replace("\\", "/").rsplit("/", 1)[-1]
    if "." not in name or name.startswith("."):
        # Dotfiles like `.env` are not editable language sources in restricted workspaces.
        return ""
    return f".{name.rsplit('.', 1)[-1].lower()}"


def editable_extensions_for(workspace_type: str) -> Optional[FrozenSet[str]]:
    """Return allowed extensions for a workspace, or ``None`` when unrestricted.

    Args:
        workspace_type: javascript | python | website.

    Returns:
        Frozen set of extensions including the leading dot, or ``None``.
    """
    workspace = (workspace_type or "").lower().strip()
    if workspace == "python":
        return PYTHON_EDITABLE_EXTENSIONS
    if workspace == "javascript":
        return JAVASCRIPT_EDITABLE_EXTENSIONS
    return None


def edit_restriction_message(workspace_type: str) -> str:
    """User-facing validation message for a restricted workspace.

    Args:
        workspace_type: javascript | python | website.

    Returns:
        Modal / API error message.
    """
    workspace = (workspace_type or "").lower().strip()
    if workspace == "python":
        return PYTHON_EDIT_MESSAGE
    if workspace == "javascript":
        return JAVASCRIPT_EDIT_MESSAGE
    return "This file type cannot be edited in the current workspace."


def is_path_editable(workspace_type: str, path: str) -> bool:
    """Whether ``path`` may be created/updated/deleted in the workspace.

    Args:
        workspace_type: Project workspace type.
        path: Project-relative file path.

    Returns:
        True when editing is allowed.
    """
    allowed = editable_extensions_for(workspace_type)
    if allowed is None:
        return True
    return _extension_of(path) in allowed


def assert_path_editable(workspace_type: str, path: str) -> None:
    """Raise ``ValidationAppError`` when ``path`` is not editable.

    Args:
        workspace_type: Project workspace type.
        path: Project-relative file path.

    Raises:
        ValidationAppError: When the extension is not allowed.
    """
    if not is_path_editable(workspace_type, path):
        raise ValidationAppError(
            edit_restriction_message(workspace_type),
            details={
                "workspace_type": (workspace_type or "").lower().strip(),
                "path": path,
                "error_code": "workspace_file_type_restricted",
            },
        )
