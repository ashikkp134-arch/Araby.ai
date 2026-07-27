"""File and folder API routes."""

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_current_user
from app.api.service_deps import get_file_service
from app.schemas.common import APIResponse
from app.schemas.file import (
    FileCreateRequest,
    FileResponse,
    FileTreeNode,
    FileUpdateRequest,
    FolderCreateRequest,
    FolderResponse,
)
from app.services.file_service import FileService

router = APIRouter(prefix="/files", tags=["files"])


@router.get("/{project_id}/tree", response_model=APIResponse[List[FileTreeNode]])
async def get_tree(
    project_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
    file_service: FileService = Depends(get_file_service),
) -> APIResponse[List[FileTreeNode]]:
    """Get nested file tree for a project.

    Args:
        project_id: Project identifier.
        current_user: Authenticated user.
        file_service: File service.

    Returns:
        Nested file tree.
    """
    tree = await file_service.list_tree(current_user["id"], project_id)
    return APIResponse(success=True, message="OK", data=tree)


@router.post("/{project_id}/folders", response_model=APIResponse[FolderResponse])
async def create_folder(
    project_id: str,
    payload: FolderCreateRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
    file_service: FileService = Depends(get_file_service),
) -> APIResponse[FolderResponse]:
    """Create a folder in a project.

    Args:
        project_id: Project identifier.
        payload: Folder payload.
        current_user: Authenticated user.
        file_service: File service.

    Returns:
        Created folder.
    """
    folder = await file_service.create_folder(current_user["id"], project_id, payload)
    return APIResponse(success=True, message="Folder created", data=folder)


@router.delete("/{project_id}/folders", response_model=APIResponse[Dict[str, Any]])
async def delete_folder(
    project_id: str,
    path: str = Query(..., description="Folder path to delete"),
    current_user: Dict[str, Any] = Depends(get_current_user),
    file_service: FileService = Depends(get_file_service),
) -> APIResponse[Dict[str, Any]]:
    """Delete a folder and nested contents.

    Args:
        project_id: Project identifier.
        path: Folder path.
        current_user: Authenticated user.
        file_service: File service.

    Returns:
        Confirmation payload.
    """
    await file_service.delete_folder(current_user["id"], project_id, path)
    return APIResponse(success=True, message="Folder deleted", data={})


@router.get("/{project_id}", response_model=APIResponse[List[FileResponse]])
async def list_files(
    project_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
    file_service: FileService = Depends(get_file_service),
) -> APIResponse[List[FileResponse]]:
    """List all files in a project.

    Args:
        project_id: Project identifier.
        current_user: Authenticated user.
        file_service: File service.

    Returns:
        Flat file list.
    """
    files = await file_service.list_files(current_user["id"], project_id)
    return APIResponse(success=True, message="OK", data=files)


@router.post("/{project_id}", response_model=APIResponse[FileResponse])
async def create_file(
    project_id: str,
    payload: FileCreateRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
    file_service: FileService = Depends(get_file_service),
) -> APIResponse[FileResponse]:
    """Create a file in a project.

    Args:
        project_id: Project identifier.
        payload: File payload.
        current_user: Authenticated user.
        file_service: File service.

    Returns:
        Created file.
    """
    file_doc = await file_service.create_file(current_user["id"], project_id, payload)
    return APIResponse(success=True, message="File created", data=file_doc)


@router.get("/{project_id}/{file_id}", response_model=APIResponse[FileResponse])
async def get_file(
    project_id: str,
    file_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
    file_service: FileService = Depends(get_file_service),
) -> APIResponse[FileResponse]:
    """Get a file by id.

    Args:
        project_id: Project identifier.
        file_id: File identifier.
        current_user: Authenticated user.
        file_service: File service.

    Returns:
        File response.
    """
    file_doc = await file_service.get_file(current_user["id"], project_id, file_id)
    return APIResponse(success=True, message="OK", data=file_doc)


@router.patch("/{project_id}/{file_id}", response_model=APIResponse[FileResponse])
async def update_file(
    project_id: str,
    file_id: str,
    payload: FileUpdateRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
    file_service: FileService = Depends(get_file_service),
) -> APIResponse[FileResponse]:
    """Update file content or rename a file.

    Args:
        project_id: Project identifier.
        file_id: File identifier.
        payload: Update payload.
        current_user: Authenticated user.
        file_service: File service.

    Returns:
        Updated file.
    """
    file_doc = await file_service.update_file(
        current_user["id"],
        project_id,
        file_id,
        payload,
    )
    return APIResponse(success=True, message="File saved", data=file_doc)


@router.delete("/{project_id}/{file_id}", response_model=APIResponse[Dict[str, Any]])
async def delete_file(
    project_id: str,
    file_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
    file_service: FileService = Depends(get_file_service),
) -> APIResponse[Dict[str, Any]]:
    """Delete a file.

    Args:
        project_id: Project identifier.
        file_id: File identifier.
        current_user: Authenticated user.
        file_service: File service.

    Returns:
        Confirmation payload.
    """
    await file_service.delete_file(current_user["id"], project_id, file_id)
    return APIResponse(success=True, message="File deleted", data={})
