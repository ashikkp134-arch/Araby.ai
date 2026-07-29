"""Apply AI-proposed file modifications with reversible change tracking."""

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from app.schemas.chat import FileChangeProposal
from app.services.file_service import FileService
from app.utils.diffing import build_file_diff
from app.utils.exceptions import AppException, ValidationAppError
from app.utils.workspace_file_policy import (
    assert_path_editable,
    edit_restriction_message,
    is_path_editable,
)

logger = logging.getLogger(__name__)


@dataclass
class ReverseChange:
    """Enough information to revert one applied file change.

    Attributes:
        path: Affected file path.
        existed_before: Whether the file existed prior to the AI change.
        previous_content: File content prior to the change (None if it did
            not exist, i.e. the AI created this file).
    """

    path: str
    existed_before: bool
    previous_content: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize for storage on the chat message document.

        Returns:
            Plain dict payload.
        """
        return {
            "path": self.path,
            "existed_before": self.existed_before,
            "previous_content": self.previous_content,
        }


def _with_diff(
    change: FileChangeProposal,
    *,
    previous_content: Optional[str],
    current_content: Optional[str],
    existed_before: bool,
) -> FileChangeProposal:
    """Return a copy of an applied change carrying its line-level diff.

    Args:
        change: Proposal that was just applied.
        previous_content: Content before the change.
        current_content: Content after the change (None for deletes).
        existed_before: Whether the file existed before the change.

    Returns:
        Copy of the proposal with ``diff`` populated.
    """
    diff = build_file_diff(
        action=change.action,
        previous_content=previous_content,
        current_content=current_content,
        existed_before=existed_before,
    )
    return change.model_copy(update={"diff": diff})


class FileModifier:
    """Apply validated file change proposals to a project."""

    def __init__(self, file_service: FileService) -> None:
        """Initialize the file modifier.

        Args:
            file_service: File service dependency.
        """
        self._files = file_service

    async def apply(
        self,
        project_id: str,
        changes: List[FileChangeProposal],
        *,
        workspace_type: str = "",
    ) -> Tuple[List[FileChangeProposal], List[ReverseChange]]:
        """Apply a list of file changes, capturing how to revert them.

        Args:
            project_id: Target project id.
            changes: Proposed changes.
            workspace_type: Project workspace type for edit-policy checks.

        Returns:
            Tuple of (successfully applied changes, reverse changes for undo).

        Raises:
            ValidationAppError: When any change targets a disallowed file type.
        """
        blocked = [
            change.path
            for change in changes
            if change.path and not is_path_editable(workspace_type, change.path)
        ]
        if blocked:
            raise ValidationAppError(
                edit_restriction_message(workspace_type),
                details={
                    "workspace_type": (workspace_type or "").lower().strip(),
                    "blocked_paths": blocked,
                    "error_code": "workspace_file_type_restricted",
                },
            )

        applied: List[FileChangeProposal] = []
        reverse: List[ReverseChange] = []
        for change in changes:
            try:
                # Belt-and-suspenders: also enforce per path (apply_path_content does too).
                assert_path_editable(workspace_type, change.path)
                previous_content = await self._files.get_raw_content_by_path(
                    project_id,
                    change.path,
                )
                existed_before = previous_content is not None

                if change.action in {"create", "update"}:
                    await self._files.apply_path_content(
                        project_id=project_id,
                        path=change.path,
                        content=change.content or "",
                        create_if_missing=True,
                    )
                    applied.append(
                        _with_diff(
                            change,
                            previous_content=previous_content,
                            current_content=change.content or "",
                            existed_before=existed_before,
                        )
                    )
                    reverse.append(
                        ReverseChange(
                            path=change.path,
                            existed_before=existed_before,
                            previous_content=previous_content,
                        )
                    )
                elif change.action == "delete":
                    if not existed_before:
                        continue
                    await self._files.delete_by_path(project_id, change.path)
                    applied.append(
                        _with_diff(
                            change,
                            previous_content=previous_content,
                            current_content=None,
                            existed_before=True,
                        )
                    )
                    reverse.append(
                        ReverseChange(
                            path=change.path,
                            existed_before=True,
                            previous_content=previous_content,
                        )
                    )
            except ValidationAppError:
                raise
            except AppException as exc:
                logger.warning(
                    "Failed to apply change %s %s: %s",
                    change.action,
                    change.path,
                    exc.message,
                )
        return applied, reverse
