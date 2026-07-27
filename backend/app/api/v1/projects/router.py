"""Project API routes."""

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_current_user
from app.api.service_deps import get_project_service
from app.schemas.common import APIResponse, PaginatedData
from app.schemas.project import (
    ProjectCreateRequest,
    ProjectImportRequest,
    ProjectResponse,
    ProjectUpdateRequest,
    WorkspaceType,
)
from app.services.project_service import ProjectService

router = APIRouter(prefix="/projects", tags=["projects"])


@router.post("", response_model=APIResponse[ProjectResponse])
async def create_project(
    payload: ProjectCreateRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
    project_service: ProjectService = Depends(get_project_service),
) -> APIResponse[ProjectResponse]:
    """Create a new project.

    Args:
        payload: Project creation payload.
        current_user: Authenticated user.
        project_service: Project service.

    Returns:
        Standard API response with created project.
    """
    project = await project_service.create(current_user["id"], payload)
    return APIResponse(success=True, message="Project created", data=project)


@router.post("/import", response_model=APIResponse[ProjectResponse])
async def import_project(
    payload: ProjectImportRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
    project_service: ProjectService = Depends(get_project_service),
) -> APIResponse[ProjectResponse]:
    """Import a local folder as a new project.

    Args:
        payload: Project metadata plus file contents.
        current_user: Authenticated user.
        project_service: Project service.

    Returns:
        Standard API response with the imported project.
    """
    project = await project_service.import_local(current_user["id"], payload)
    return APIResponse(success=True, message="Project imported", data=project)


@router.get("", response_model=APIResponse[PaginatedData[ProjectResponse]])
async def list_projects(
    workspace_type: Optional[WorkspaceType] = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: Dict[str, Any] = Depends(get_current_user),
    project_service: ProjectService = Depends(get_project_service),
) -> APIResponse[PaginatedData[ProjectResponse]]:
    """List projects for the current user.

    Args:
        workspace_type: Optional workspace filter.
        page: Page number.
        page_size: Page size.
        current_user: Authenticated user.
        project_service: Project service.

    Returns:
        Paginated project list.
    """
    data = await project_service.list_projects(
        current_user["id"],
        workspace_type,
        page,
        page_size,
    )
    return APIResponse(success=True, message="OK", data=data)


@router.get("/{project_id}", response_model=APIResponse[ProjectResponse])
async def get_project(
    project_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
    project_service: ProjectService = Depends(get_project_service),
) -> APIResponse[ProjectResponse]:
    """Get a project by id.

    Args:
        project_id: Project identifier.
        current_user: Authenticated user.
        project_service: Project service.

    Returns:
        Project response.
    """
    project = await project_service.get(current_user["id"], project_id)
    return APIResponse(success=True, message="OK", data=project)


@router.patch("/{project_id}", response_model=APIResponse[ProjectResponse])
async def update_project(
    project_id: str,
    payload: ProjectUpdateRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
    project_service: ProjectService = Depends(get_project_service),
) -> APIResponse[ProjectResponse]:
    """Update project metadata.

    Args:
        project_id: Project identifier.
        payload: Update payload.
        current_user: Authenticated user.
        project_service: Project service.

    Returns:
        Updated project response.
    """
    project = await project_service.update(current_user["id"], project_id, payload)
    return APIResponse(success=True, message="Project updated", data=project)


@router.delete("/{project_id}", response_model=APIResponse[Dict[str, Any]])
async def delete_project(
    project_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
    project_service: ProjectService = Depends(get_project_service),
) -> APIResponse[Dict[str, Any]]:
    """Delete a project.

    Args:
        project_id: Project identifier.
        current_user: Authenticated user.
        project_service: Project service.

    Returns:
        Confirmation payload.
    """
    await project_service.delete(current_user["id"], project_id)
    return APIResponse(success=True, message="Project deleted", data={})
