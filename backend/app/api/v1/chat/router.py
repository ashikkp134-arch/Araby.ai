"""Chat API routes."""

from typing import Any, Dict

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_current_user
from app.api.service_deps import get_chat_service
from app.schemas.chat import (
    ChatCompletionResponse,
    ChatMessageRequest,
    ChatMessageResponse,
    UndoChangesResponse,
)
from app.schemas.common import APIResponse, PaginatedData
from app.services.chat_service import ChatService

router = APIRouter(prefix="/chat", tags=["chat"])


@router.get("/{project_id}/messages", response_model=APIResponse[PaginatedData[ChatMessageResponse]])
async def list_messages(
    project_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    current_user: Dict[str, Any] = Depends(get_current_user),
    chat_service: ChatService = Depends(get_chat_service),
) -> APIResponse[PaginatedData[ChatMessageResponse]]:
    """List chat history for a project.

    Args:
        project_id: Project identifier.
        page: Page number.
        page_size: Page size.
        current_user: Authenticated user.
        chat_service: Chat service.

    Returns:
        Paginated chat messages.
    """
    data = await chat_service.list_messages(current_user["id"], project_id, page, page_size)
    return APIResponse(success=True, message="OK", data=data)


@router.post("/{project_id}/messages", response_model=APIResponse[ChatCompletionResponse])
async def send_message(
    project_id: str,
    payload: ChatMessageRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
    chat_service: ChatService = Depends(get_chat_service),
) -> APIResponse[ChatCompletionResponse]:
    """Send a chat message and receive an AI response.

    Args:
        project_id: Project identifier.
        payload: Chat message payload.
        current_user: Authenticated user.
        chat_service: Chat service.

    Returns:
        Chat completion response.
    """
    data = await chat_service.send_message(current_user["id"], project_id, payload)
    return APIResponse(success=True, message="OK", data=data)


@router.post("/{project_id}/undo-last", response_model=APIResponse[UndoChangesResponse])
async def undo_last_changes(
    project_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
    chat_service: ChatService = Depends(get_chat_service),
) -> APIResponse[UndoChangesResponse]:
    """Revert every file change from the most recent AI change set.

    Args:
        project_id: Project identifier.
        current_user: Authenticated user.
        chat_service: Chat service.

    Returns:
        Summary of restored/removed file paths.
    """
    data = await chat_service.undo_last_changes(current_user["id"], project_id)
    return APIResponse(success=True, message="OK", data=data)
