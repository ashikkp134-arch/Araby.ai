"""Project management service."""

import logging
from typing import Any, Dict, Optional

from app.core.redis import RedisCache
from app.repositories.chat_repository import ChatRepository
from app.repositories.file_repository import FileRepository, FolderRepository
from app.repositories.project_repository import ProjectRepository
from app.schemas.common import PaginatedData
from app.schemas.project import (
    ProjectCreateRequest,
    ProjectImportRequest,
    ProjectResponse,
    ProjectUpdateRequest,
    WorkspaceType,
)
from app.utils.exceptions import ForbiddenError, NotFoundError, ValidationAppError
from app.utils.files import (
    basename_of,
    default_files_for_workspace,
    detect_language,
    normalize_path,
    parent_path_of,
    sanitize_name,
)
from app.utils.object_id import parse_object_id
from app.utils.pagination import build_pagination, clamp_pagination

logger = logging.getLogger(__name__)


class ProjectService:
    """Business logic for project CRUD and ownership checks."""

    def __init__(
        self,
        project_repo: ProjectRepository,
        file_repo: FileRepository,
        folder_repo: FolderRepository,
        chat_repo: ChatRepository,
        cache: RedisCache,
    ) -> None:
        """Initialize the project service.

        Args:
            project_repo: Project repository.
            file_repo: File repository.
            folder_repo: Folder repository.
            chat_repo: Chat repository.
            cache: Redis cache helper.
        """
        self._projects = project_repo
        self._files = file_repo
        self._folders = folder_repo
        self._chat = chat_repo
        self._cache = cache

    async def create(self, user_id: str, payload: ProjectCreateRequest) -> ProjectResponse:
        """Create a project with starter files.

        Args:
            user_id: Owner user id.
            payload: Creation payload.

        Returns:
            Created project response.
        """
        project = await self._projects.create(
            user_id=parse_object_id(user_id, "user_id"),
            name=payload.name,
            description=payload.description,
            workspace_type=payload.workspace_type,
        )
        project_oid = parse_object_id(project["id"], "project_id")
        for starter in default_files_for_workspace(payload.workspace_type.value):
            await self._files.create(
                project_id=project_oid,
                name=starter["name"],
                path=starter["name"],
                content=starter["content"],
                language=detect_language(starter["name"]),
            )
        await self._chat.get_or_create_session(project_oid, parse_object_id(user_id, "user_id"))
        await self._cache.delete(f"projects:user:{user_id}")
        logger.info("Project created %s for user %s", project["id"], user_id)
        return ProjectResponse(**project)

    async def import_local(self, user_id: str, payload: ProjectImportRequest) -> ProjectResponse:
        """Create a project from a local folder file list.

        Skips default starter files and seeds the provided paths instead so
        the user can edit and chat against their existing codebase.

        Args:
            user_id: Owner user id.
            payload: Import payload with workspace metadata and files.

        Returns:
            Created project response.

        Raises:
            ValidationAppError: If paths are invalid or the batch is empty after filtering.
        """
        # Deduplicate by normalized path (last write wins) and validate segments.
        unique_files: Dict[str, str] = {}
        total_bytes = 0
        for item in payload.files:
            path = normalize_path(item.path)
            if not path:
                raise ValidationAppError("Invalid file path in import")
            for segment in path.split("/"):
                sanitize_name(segment)
            content = item.content if item.content is not None else ""
            total_bytes += len(content.encode("utf-8", errors="ignore"))
            if total_bytes > 5_242_880:
                raise ValidationAppError("Imported project exceeds the 5MB text limit")
            unique_files[path] = content

        if not unique_files:
            raise ValidationAppError("No importable files found")

        project = await self._projects.create(
            user_id=parse_object_id(user_id, "user_id"),
            name=payload.name,
            description=payload.description or "Imported from local folder",
            workspace_type=payload.workspace_type,
        )
        project_oid = parse_object_id(project["id"], "project_id")

        # Create folders depth-first, then files.
        folder_paths = sorted(
            {parent_path_of(path) for path in unique_files if parent_path_of(path)},
            key=lambda p: p.count("/"),
        )
        folder_ids: Dict[str, Any] = {}
        for folder_path in folder_paths:
            parts = folder_path.split("/")
            current = ""
            parent_id = None
            for part in parts:
                current = f"{current}/{part}" if current else part
                if current in folder_ids:
                    parent_id = folder_ids[current]
                    continue
                existing = await self._folders.find_by_path(project_oid, current)
                if existing:
                    folder_ids[current] = existing["_id"]
                    parent_id = existing["_id"]
                    continue
                created = await self._folders.create(project_oid, part, current, parent_id)
                folder_oid = parse_object_id(created["id"], "folder_id")
                folder_ids[current] = folder_oid
                parent_id = folder_oid

        for path, content in sorted(unique_files.items()):
            parent = parent_path_of(path)
            folder_id = folder_ids.get(parent) if parent else None
            await self._files.create(
                project_id=project_oid,
                name=basename_of(path),
                path=path,
                content=content,
                language=detect_language(basename_of(path)),
                folder_id=folder_id,
            )

        await self._chat.get_or_create_session(project_oid, parse_object_id(user_id, "user_id"))
        await self._cache.delete(f"projects:user:{user_id}")
        logger.info(
            "Project imported %s for user %s (%s files)",
            project["id"],
            user_id,
            len(unique_files),
        )
        return ProjectResponse(**project)

    async def list_projects(
        self,
        user_id: str,
        workspace_type: Optional[WorkspaceType],
        page: int,
        page_size: int,
    ) -> PaginatedData[ProjectResponse]:
        """List projects for the authenticated user.

        Args:
            user_id: Owner user id.
            workspace_type: Optional workspace filter.
            page: Page number.
            page_size: Page size.

        Returns:
            Paginated project responses.
        """
        page, page_size = clamp_pagination(page, page_size)
        items, total = await self._projects.list_for_user(
            user_id=parse_object_id(user_id, "user_id"),
            workspace_type=workspace_type.value if workspace_type else None,
            skip=(page - 1) * page_size,
            limit=page_size,
        )
        return PaginatedData(
            items=[ProjectResponse(**item) for item in items],
            pagination=build_pagination(page, page_size, total),
        )

    async def get(self, user_id: str, project_id: str) -> ProjectResponse:
        """Fetch a project ensuring ownership.

        Args:
            user_id: Owner user id.
            project_id: Project id.

        Returns:
            Project response.
        """
        project = await self._require_owned_project(user_id, project_id)
        return ProjectResponse(**{
            "id": str(project["_id"]),
            "name": project["name"],
            "description": project["description"],
            "workspace_type": project["workspace_type"],
            "user_id": str(project["user_id"]),
            "created_at": project["created_at"],
            "updated_at": project["updated_at"],
        })

    async def update(
        self,
        user_id: str,
        project_id: str,
        payload: ProjectUpdateRequest,
    ) -> ProjectResponse:
        """Update project metadata.

        Args:
            user_id: Owner user id.
            project_id: Project id.
            payload: Update payload.

        Returns:
            Updated project response.
        """
        await self._require_owned_project(user_id, project_id)
        updates: Dict[str, Any] = {}
        if payload.name is not None:
            updates["name"] = payload.name
        if payload.description is not None:
            updates["description"] = payload.description
        updated = await self._projects.update(
            parse_object_id(project_id, "project_id"),
            parse_object_id(user_id, "user_id"),
            updates,
        )
        if not updated:
            raise NotFoundError("Project not found")
        await self._cache.delete(f"projects:user:{user_id}")
        return ProjectResponse(**updated)

    async def delete(self, user_id: str, project_id: str) -> None:
        """Delete a project and related data.

        Args:
            user_id: Owner user id.
            project_id: Project id.
        """
        await self._require_owned_project(user_id, project_id)
        project_oid = parse_object_id(project_id, "project_id")
        await self._files.delete_by_project(project_oid)
        await self._folders.delete_by_project(project_oid)
        await self._chat.delete_for_project(project_oid)
        deleted = await self._projects.delete(project_oid, parse_object_id(user_id, "user_id"))
        if not deleted:
            raise NotFoundError("Project not found")
        await self._cache.delete(f"projects:user:{user_id}")
        await self._cache.delete(f"ai:context:{project_id}")
        logger.info("Project deleted %s", project_id)

    async def ensure_owned(self, user_id: str, project_id: str) -> Dict[str, Any]:
        """Public ownership check used by other services.

        Args:
            user_id: Owner user id.
            project_id: Project id.

        Returns:
            Raw project document.
        """
        return await self._require_owned_project(user_id, project_id)

    async def _require_owned_project(self, user_id: str, project_id: str) -> Dict[str, Any]:
        """Load a project and verify ownership.

        Args:
            user_id: Owner user id.
            project_id: Project id.

        Returns:
            Raw project document.

        Raises:
            NotFoundError: If project does not exist.
            ForbiddenError: If the user does not own the project.
        """
        project = await self._projects.find_by_id(parse_object_id(project_id, "project_id"))
        if not project:
            raise NotFoundError("Project not found")
        if str(project["user_id"]) != user_id:
            raise ForbiddenError("You do not have access to this project")
        return project
