"""Workspace catalog API routes."""

from typing import List

from fastapi import APIRouter, Depends

from app.api.service_deps import get_workspace_service
from app.schemas.common import APIResponse
from app.schemas.project import WorkspaceInfo
from app.services.workspace_service import WorkspaceService

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


@router.get("", response_model=APIResponse[List[WorkspaceInfo]])
async def list_workspaces(
    workspace_service: WorkspaceService = Depends(get_workspace_service),
) -> APIResponse[List[WorkspaceInfo]]:
    """List available workspace cards.

    Args:
        workspace_service: Workspace service.

    Returns:
        Workspace catalog.
    """
    data = workspace_service.list_workspaces()
    return APIResponse(success=True, message="OK", data=data)
