"""Apply AI-proposed file modifications."""

import logging
from typing import List

from app.schemas.chat import FileChangeProposal
from app.services.file_service import FileService
from app.utils.exceptions import AppException

logger = logging.getLogger(__name__)


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
    ) -> List[FileChangeProposal]:
        """Apply a list of file changes.

        Args:
            project_id: Target project id.
            changes: Proposed changes.

        Returns:
            Successfully applied changes.
        """
        applied: List[FileChangeProposal] = []
        for change in changes:
            try:
                if change.action in {"create", "update"}:
                    await self._files.apply_path_content(
                        project_id=project_id,
                        path=change.path,
                        content=change.content or "",
                        create_if_missing=True,
                    )
                    applied.append(change)
                elif change.action == "delete":
                    await self._files.delete_by_path(project_id, change.path)
                    applied.append(change)
            except AppException as exc:
                logger.warning(
                    "Failed to apply change %s %s: %s",
                    change.action,
                    change.path,
                    exc.message,
                )
        return applied
