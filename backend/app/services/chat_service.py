"""Chat history and AI turn service."""

import logging

from app.ai.pipelines.chat_pipeline import AIPipeline
from app.repositories.chat_repository import ChatRepository
from app.schemas.chat import (
    ChatCompletionResponse,
    ChatMessageRequest,
    ChatMessageResponse,
    UndoChangesResponse,
)
from app.schemas.common import PaginatedData
from app.services.file_service import FileService
from app.services.project_service import ProjectService
from app.utils.exceptions import AppException, NotFoundError
from app.utils.object_id import parse_object_id
from app.utils.pagination import build_pagination, clamp_pagination

logger = logging.getLogger(__name__)


class ChatService:
    """Business logic for project chat history and AI completion."""

    def __init__(
        self,
        chat_repo: ChatRepository,
        project_service: ProjectService,
        ai_pipeline: AIPipeline,
        file_service: FileService,
    ) -> None:
        """Initialize the chat service.

        Args:
            chat_repo: Chat repository.
            project_service: Project service.
            ai_pipeline: AI pipeline orchestrator.
            file_service: File service used to apply undo operations.
        """
        self._chat = chat_repo
        self._projects = project_service
        self._pipeline = ai_pipeline
        self._files = file_service

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

    async def undo_last_changes(self, user_id: str, project_id: str) -> UndoChangesResponse:
        """Revert every file change from the most recent AI change set.

        Args:
            user_id: Authenticated user id.
            project_id: Project id.

        Returns:
            Summary of restored/removed file paths.

        Raises:
            NotFoundError: When there is no AI change set left to undo.
        """
        await self._projects.ensure_owned(user_id, project_id)
        project_oid = parse_object_id(project_id, "project_id")
        message = await self._chat.find_latest_undoable_message(project_oid)
        if not message:
            raise NotFoundError("No AI changes available to undo")

        reverse_changes = message.get("reverse_changes") or []
        restored: list[str] = []
        for item in reverse_changes:
            path = item.get("path")
            if not path:
                continue
            try:
                if item.get("existed_before"):
                    await self._files.apply_path_content(
                        project_id=project_id,
                        path=path,
                        content=item.get("previous_content") or "",
                        create_if_missing=True,
                    )
                else:
                    await self._files.delete_by_path(project_id, path)
                restored.append(path)
            except AppException as exc:
                logger.warning("Failed to revert %s during undo: %s", path, exc.message)

        await self._chat.mark_undone(parse_object_id(message["id"], "message_id"))
        return UndoChangesResponse(message_id=message["id"], restored_paths=restored)
