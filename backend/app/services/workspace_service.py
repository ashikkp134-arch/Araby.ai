"""Workspace catalog service."""

from typing import List

from app.schemas.project import WorkspaceInfo, WorkspaceType


class WorkspaceService:
    """Provide workspace card metadata."""

    def list_workspaces(self) -> List[WorkspaceInfo]:
        """Return the three supported workspace cards.

        Returns:
            List of WorkspaceInfo objects.
        """
        return [
            WorkspaceInfo(
                type=WorkspaceType.JAVASCRIPT,
                title="JavaScript Workspace",
                description="Build and iterate on JavaScript projects with AI assistance.",
                language_hint="JavaScript",
            ),
            WorkspaceInfo(
                type=WorkspaceType.PYTHON,
                title="Python Workspace",
                description="Create Python applications with multi-file support and AI chat.",
                language_hint="Python",
            ),
            WorkspaceInfo(
                type=WorkspaceType.WEBSITE,
                title="Website Builder",
                description="Design websites with HTML, CSS, JavaScript, and Tailwind CSS.",
                language_hint="HTML/CSS/JS + Tailwind",
            ),
        ]
