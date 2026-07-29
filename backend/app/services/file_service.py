"""File and folder management service."""

import json
import logging
from typing import Any, Dict, List, Optional

from app.core.redis import RedisCache
from app.repositories.file_repository import FileRepository, FolderRepository
from app.repositories.project_repository import ProjectRepository
from app.schemas.file import (
    FileCreateRequest,
    FileResponse,
    FileTreeNode,
    FileUpdateRequest,
    FolderCreateRequest,
    FolderResponse,
)
from app.services.project_service import ProjectService
from app.utils.exceptions import ConflictError, NotFoundError, ValidationAppError
from app.utils.files import (
    basename_of,
    detect_language,
    join_path,
    normalize_path,
    parent_path_of,
    sanitize_name,
)
from app.utils.object_id import parse_object_id
from app.utils.workspace_file_policy import assert_path_editable

logger = logging.getLogger(__name__)


class FileService:
    """Business logic for nested files and folders."""

    def __init__(
        self,
        file_repo: FileRepository,
        folder_repo: FolderRepository,
        project_repo: ProjectRepository,
        project_service: ProjectService,
        cache: RedisCache,
    ) -> None:
        """Initialize the file service.

        Args:
            file_repo: File repository.
            folder_repo: Folder repository.
            project_repo: Project repository.
            project_service: Project service for ownership checks.
            cache: Redis cache helper.
        """
        self._files = file_repo
        self._folders = folder_repo
        self._projects = project_repo
        self._project_service = project_service
        self._cache = cache

    async def create_folder(
        self,
        user_id: str,
        project_id: str,
        payload: FolderCreateRequest,
    ) -> FolderResponse:
        """Create a folder inside a project.

        Args:
            user_id: Owner user id.
            project_id: Project id.
            payload: Folder creation payload.

        Returns:
            Created folder response.
        """
        await self._project_service.ensure_owned(user_id, project_id)
        project_oid = parse_object_id(project_id, "project_id")
        parent_path = normalize_path(payload.parent_path)
        name = sanitize_name(payload.name)
        path = join_path(parent_path, name)
        if await self._folders.find_by_path(project_oid, path):
            raise ConflictError("Folder already exists")
        parent_id = None
        if parent_path:
            parent = await self._folders.find_by_path(project_oid, parent_path)
            if not parent:
                raise NotFoundError("Parent folder not found")
            parent_id = parent["_id"]
        folder = await self._folders.create(project_oid, name, path, parent_id)
        await self._projects.touch(project_oid)
        await self._invalidate_project_cache(project_id)
        return FolderResponse(**folder)

    async def create_file(
        self,
        user_id: str,
        project_id: str,
        payload: FileCreateRequest,
    ) -> FileResponse:
        """Create a file inside a project.

        Args:
            user_id: Owner user id.
            project_id: Project id.
            payload: File creation payload.

        Returns:
            Created file response.
        """
        project = await self._project_service.ensure_owned(user_id, project_id)
        project_oid = parse_object_id(project_id, "project_id")
        folder_path = normalize_path(payload.folder_path)
        name = sanitize_name(payload.name)
        path = join_path(folder_path, name)
        assert_path_editable(str(project.get("workspace_type") or ""), path)
        if await self._files.find_by_path(project_oid, path):
            raise ConflictError("File already exists")
        folder_id = None
        if folder_path:
            folder = await self._folders.find_by_path(project_oid, folder_path)
            if not folder:
                raise NotFoundError("Parent folder not found")
            folder_id = folder["_id"]
        file_doc = await self._files.create(
            project_id=project_oid,
            name=name,
            path=path,
            content=payload.content,
            language=detect_language(name),
            folder_id=folder_id,
        )
        await self._projects.touch(project_oid)
        await self._invalidate_project_cache(project_id)
        await self._cache.set(f"recent:file:{user_id}:{project_id}", path, 3600)
        return FileResponse(**file_doc)

    async def get_file(self, user_id: str, project_id: str, file_id: str) -> FileResponse:
        """Fetch a single file.

        Args:
            user_id: Owner user id.
            project_id: Project id.
            file_id: File id.

        Returns:
            File response.
        """
        await self._project_service.ensure_owned(user_id, project_id)
        file_doc = await self._files.find_by_id(parse_object_id(file_id, "file_id"))
        if not file_doc or str(file_doc["project_id"]) != project_id:
            raise NotFoundError("File not found")
        serialized = {
            "id": str(file_doc["_id"]),
            "project_id": str(file_doc["project_id"]),
            "name": file_doc["name"],
            "path": file_doc["path"],
            "folder_id": str(file_doc["folder_id"]) if file_doc.get("folder_id") else None,
            "content": file_doc["content"],
            "language": file_doc["language"],
            "updated_at": file_doc["updated_at"],
            "created_at": file_doc["created_at"],
        }
        await self._cache.set(f"recent:file:{user_id}:{project_id}", file_doc["path"], 3600)
        return FileResponse(**serialized)

    async def update_file(
        self,
        user_id: str,
        project_id: str,
        file_id: str,
        payload: FileUpdateRequest,
    ) -> FileResponse:
        """Update file content and/or rename a file.

        Args:
            user_id: Owner user id.
            project_id: Project id.
            file_id: File id.
            payload: Update payload.

        Returns:
            Updated file response.
        """
        project = await self._project_service.ensure_owned(user_id, project_id)
        file_oid = parse_object_id(file_id, "file_id")
        existing = await self._files.find_by_id(file_oid)
        if not existing or str(existing["project_id"]) != project_id:
            raise NotFoundError("File not found")
        workspace_type = str(project.get("workspace_type") or "")
        updates: Dict[str, Any] = {}
        if payload.content is not None:
            assert_path_editable(workspace_type, str(existing.get("path") or ""))
            updates["content"] = payload.content
        if payload.name is not None:
            new_name = sanitize_name(payload.name)
            parent = parent_path_of(existing["path"])
            new_path = join_path(parent, new_name)
            assert_path_editable(workspace_type, new_path)
            # Renaming an already-restricted source to another allowed type is fine;
            # renaming into a disallowed extension is blocked above.
            conflict = await self._files.find_by_path(
                parse_object_id(project_id, "project_id"),
                new_path,
            )
            if conflict and str(conflict["_id"]) != file_id:
                raise ConflictError("A file with that name already exists")
            updates["name"] = new_name
            updates["path"] = new_path
            updates["language"] = detect_language(new_name)
        updated = await self._files.update(file_oid, updates)
        if not updated:
            raise NotFoundError("File not found")
        await self._projects.touch(parse_object_id(project_id, "project_id"))
        await self._invalidate_project_cache(project_id)
        return FileResponse(**updated)

    async def delete_file(self, user_id: str, project_id: str, file_id: str) -> None:
        """Delete a file.

        Args:
            user_id: Owner user id.
            project_id: Project id.
            file_id: File id.
        """
        project = await self._project_service.ensure_owned(user_id, project_id)
        file_doc = await self._files.find_by_id(parse_object_id(file_id, "file_id"))
        if not file_doc or str(file_doc["project_id"]) != project_id:
            raise NotFoundError("File not found")
        assert_path_editable(
            str(project.get("workspace_type") or ""),
            str(file_doc.get("path") or ""),
        )
        await self._files.delete(parse_object_id(file_id, "file_id"))
        await self._projects.touch(parse_object_id(project_id, "project_id"))
        await self._invalidate_project_cache(project_id)

    async def delete_folder(self, user_id: str, project_id: str, folder_path: str) -> None:
        """Delete a folder and all nested contents.

        Args:
            user_id: Owner user id.
            project_id: Project id.
            folder_path: Folder path to delete.
        """
        await self._project_service.ensure_owned(user_id, project_id)
        path = normalize_path(folder_path)
        if not path:
            raise ValidationAppError("Cannot delete project root")
        project_oid = parse_object_id(project_id, "project_id")
        folder = await self._folders.find_by_path(project_oid, path)
        if not folder:
            raise NotFoundError("Folder not found")
        await self._files.delete_by_prefix(project_oid, path)
        await self._folders.delete_by_prefix(project_oid, path)
        await self._projects.touch(project_oid)
        await self._invalidate_project_cache(project_id)

    async def list_tree(self, user_id: str, project_id: str) -> List[FileTreeNode]:
        """Build a nested file/folder tree for a project.

        Args:
            user_id: Owner user id.
            project_id: Project id.

        Returns:
            Nested file tree nodes.
        """
        await self._project_service.ensure_owned(user_id, project_id)
        cache_key = f"project:tree:{project_id}"
        cached = await self._cache.get(cache_key)
        if cached:
            raw = json.loads(cached)
            return [FileTreeNode.model_validate(item) for item in raw]
        project_oid = parse_object_id(project_id, "project_id")
        folders = await self._folders.list_for_project(project_oid)
        files = await self._files.list_for_project(project_oid)
        tree = self._build_tree(folders, files)
        await self._cache.set(
            cache_key,
            json.dumps([node.model_dump(mode="json") for node in tree]),
            60,
        )
        return tree

    async def list_files(self, user_id: str, project_id: str) -> List[FileResponse]:
        """List all files for a project (flat).

        Args:
            user_id: Owner user id.
            project_id: Project id.

        Returns:
            Flat list of file responses.
        """
        await self._project_service.ensure_owned(user_id, project_id)
        files = await self._files.list_for_project(parse_object_id(project_id, "project_id"))
        return [FileResponse(**item) for item in files]

    async def apply_path_content(
        self,
        project_id: str,
        path: str,
        content: str,
        create_if_missing: bool = True,
    ) -> FileResponse:
        """Create or update a file by path (used by AI file modifier).

        Args:
            project_id: Project id.
            path: Target file path.
            content: New file content.
            create_if_missing: Whether to create missing files.

        Returns:
            Upserted file response.
        """
        project_oid = parse_object_id(project_id, "project_id")
        normalized = normalize_path(path)
        if not normalized:
            raise ValidationAppError("Invalid file path")
        project = await self._projects.find_by_id(project_oid)
        if project:
            assert_path_editable(str(project.get("workspace_type") or ""), normalized)
        existing = await self._files.find_by_path(project_oid, normalized)
        if existing:
            updated = await self._files.update(existing["_id"], {"content": content})
            await self._invalidate_project_cache(project_id)
            return FileResponse(**updated)  # type: ignore[arg-type]
        if not create_if_missing:
            raise NotFoundError("File not found")
        parent = parent_path_of(normalized)
        name = basename_of(normalized)
        folder_id = None
        if parent:
            folder = await self._folders.find_by_path(project_oid, parent)
            if not folder:
                folder = await self._ensure_folder_path(project_oid, parent)
            folder_id = folder["_id"] if "_id" in folder else parse_object_id(folder["id"], "folder_id")
        created = await self._files.create(
            project_id=project_oid,
            name=name,
            path=normalized,
            content=content,
            language=detect_language(name),
            folder_id=folder_id,
        )
        await self._invalidate_project_cache(project_id)
        return FileResponse(**created)

    async def get_raw_content_by_path(self, project_id: str, path: str) -> Optional[str]:
        """Fetch a file's content by path without ownership checks.

        Used internally by the AI file modifier / undo flow, which already
        operates on a pre-validated project id.

        Args:
            project_id: Project id.
            path: File path.

        Returns:
            File content, or None if no file exists at that path.
        """
        project_oid = parse_object_id(project_id, "project_id")
        normalized = normalize_path(path)
        if not normalized:
            return None
        existing = await self._files.find_by_path(project_oid, normalized)
        return existing["content"] if existing else None

    async def delete_by_path(self, project_id: str, path: str) -> None:
        """Delete a file by path.

        Args:
            project_id: Project id.
            path: File path.
        """
        project_oid = parse_object_id(project_id, "project_id")
        existing = await self._files.find_by_path(project_oid, normalize_path(path))
        if not existing:
            raise NotFoundError("File not found")
        project = await self._projects.find_by_id(project_oid)
        if project:
            assert_path_editable(
                str(project.get("workspace_type") or ""),
                str(existing.get("path") or path),
            )
        await self._files.delete(existing["_id"])
        await self._invalidate_project_cache(project_id)

    async def _ensure_folder_path(self, project_oid: Any, path: str) -> Dict[str, Any]:
        """Ensure nested folders exist for a path.

        Args:
            project_oid: Project ObjectId.
            path: Folder path.

        Returns:
            Final folder document (raw or serialized).
        """
        parts = [part for part in path.split("/") if part]
        current = ""
        parent_id = None
        folder: Optional[Dict[str, Any]] = None
        for part in parts:
            current = f"{current}/{part}" if current else part
            folder = await self._folders.find_by_path(project_oid, current)
            if not folder:
                created = await self._folders.create(project_oid, part, current, parent_id)
                folder = {"_id": parse_object_id(created["id"], "folder_id"), **created}
            parent_id = folder["_id"]
        assert folder is not None
        return folder

    def _build_tree(
        self,
        folders: List[Dict[str, Any]],
        files: List[Dict[str, Any]],
    ) -> List[FileTreeNode]:
        """Construct a nested tree from flat folder/file lists.

        Args:
            folders: Serialized folders.
            files: Serialized files.

        Returns:
            Root-level tree nodes.
        """
        nodes: Dict[str, FileTreeNode] = {}
        for folder in folders:
            nodes[folder["path"]] = FileTreeNode(
                id=folder["id"],
                name=folder["name"],
                path=folder["path"],
                type="folder",
                children=[],
            )
        roots: List[FileTreeNode] = []
        for folder in folders:
            parent = parent_path_of(folder["path"])
            node = nodes[folder["path"]]
            if parent and parent in nodes:
                assert nodes[parent].children is not None
                nodes[parent].children.append(node)  # type: ignore[union-attr]
            else:
                roots.append(node)
        for file_doc in files:
            file_node = FileTreeNode(
                id=file_doc["id"],
                name=file_doc["name"],
                path=file_doc["path"],
                type="file",
                language=file_doc.get("language"),
            )
            parent = parent_path_of(file_doc["path"])
            if parent and parent in nodes:
                assert nodes[parent].children is not None
                nodes[parent].children.append(file_node)  # type: ignore[union-attr]
            else:
                roots.append(file_node)

        def sort_nodes(items: List[FileTreeNode]) -> List[FileTreeNode]:
            items.sort(key=lambda n: (0 if n.type == "folder" else 1, n.name.lower()))
            for item in items:
                if item.children:
                    item.children = sort_nodes(item.children)
            return items

        return sort_nodes(roots)

    async def _invalidate_project_cache(self, project_id: str) -> None:
        """Invalidate cached project tree and AI context.

        Args:
            project_id: Project id.
        """
        await self._cache.delete(f"project:tree:{project_id}")
        await self._cache.delete(f"ai:context:{project_id}")
