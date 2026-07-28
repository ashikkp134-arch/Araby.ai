"""Chat history and AI turn service."""

from typing import Optional

from app.ai.pipelines.chat_pipeline import AIPipeline
from app.repositories.chat_repository import ChatRepository
from app.schemas.chat import ChatCompletionResponse, ChatMessageRequest, ChatMessageResponse
from app.schemas.common import PaginatedData
from app.services.project_service import ProjectService
from app.utils.object_id import parse_object_id
from app.utils.pagination import build_pagination, clamp_pagination


class ChatService:
    """Business logic for project chat history and AI completion."""

    def __init__(
        self,
        chat_repo: ChatRepository,
        project_service: ProjectService,
        ai_pipeline: AIPipeline,
    ) -> None:
        """Initialize the chat service.

        Args:
            chat_repo: Chat repository.
            project_service: Project service.
            ai_pipeline: AI pipeline orchestrator.
        """
        self._chat = chat_repo
        self._projects = project_service
        self._pipeline = ai_pipeline

    async def list_messages(
        self,
        user_id: str,
        project_id: str,
        page: int,
        page_size: int,
    ) -> PaginatedData[ChatMessageResponse]:
        """List chat messages for a project.

        Args:
            user_id: Authenticated user id.
            project_id: Project id.
            page: Page number.
            page_size: Page size.

        Returns:
            Paginated chat messages.
        """
        await self._projects.ensure_owned(user_id, project_id)
        session = await self._chat.get_or_create_session(
            parse_object_id(project_id, "project_id"),
            parse_object_id(user_id, "user_id"),
        )
        page, page_size = clamp_pagination(page, page_size)
        items, total = await self._chat.list_messages(
            parse_object_id(session["id"], "session_id"),
            skip=(page - 1) * page_size,
            limit=page_size,
        )
        return PaginatedData(
            items=[ChatMessageResponse(**item) for item in items],
            pagination=build_pagination(page, page_size, total),
        )

    async def send_message(
        self,
        user_id: str,
        project_id: str,
        payload: ChatMessageRequest,
    ) -> ChatCompletionResponse:
        """Send a user message through the AI pipeline.

        Args:
            user_id: Authenticated user id.
            project_id: Project id.
            payload: Chat message payload.

        Returns:
            Chat completion response.
        """
        return await self._pipeline.run(
            user_id=user_id,
            project_id=project_id,
            content=payload.content,
            current_file_path=payload.current_file_path,
            selected_code=payload.selected_code,
            apply_changes=payload.apply_changes,
            open_tabs=payload.open_tabs,
        )
