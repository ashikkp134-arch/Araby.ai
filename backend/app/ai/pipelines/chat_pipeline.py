"""End-to-end AI chat pipeline."""

import logging
import time
from typing import Any, Dict, List, Optional

from app.ai.context.builder import ContextBuilder
from app.ai.pipelines.file_modifier import FileModifier
from app.ai.pipelines.response_parser import ResponseParser
from app.ai.prompts.builder import PromptBuilder
from app.ai.providers.base import LLMProvider
from app.ai.providers.factory import get_llm_provider
from app.core.redis import RedisCache
from app.repositories.chat_repository import ChatRepository
from app.repositories.file_repository import FileRepository, FolderRepository
from app.schemas.chat import ChatCompletionResponse, ChatMessageResponse, FileChangeProposal
from app.services.file_service import FileService
from app.services.project_service import ProjectService
from app.utils.object_id import parse_object_id

logger = logging.getLogger(__name__)


class AIPipeline:
    """Orchestrate prompt/context/LLM/parse/modify for chat turns."""

    def __init__(
        self,
        project_service: ProjectService,
        file_service: FileService,
        file_repo: FileRepository,
        folder_repo: FolderRepository,
        chat_repo: ChatRepository,
        cache: RedisCache,
        provider: Optional[LLMProvider] = None,
    ) -> None:
        """Initialize the AI pipeline.

        Args:
            project_service: Project ownership service.
            file_service: File management service.
            file_repo: File repository.
            folder_repo: Folder repository.
            chat_repo: Chat repository.
            cache: Redis cache.
            provider: Optional LLM provider override.
        """
        self._projects = project_service
        self._file_service = file_service
        self._files = file_repo
        self._folders = folder_repo
        self._chat = chat_repo
        self._cache = cache
        self._provider = provider or get_llm_provider()
        self._context_builder = ContextBuilder(cache)
        self._prompt_builder = PromptBuilder()
        self._parser = ResponseParser()
        self._modifier = FileModifier(file_service)

    async def run(
        self,
        user_id: str,
        project_id: str,
        content: str,
        current_file_path: Optional[str] = None,
        selected_code: Optional[str] = None,
        apply_changes: bool = True,
    ) -> ChatCompletionResponse:
        """Execute a full AI chat turn.

        Args:
            user_id: Authenticated user id.
            project_id: Target project id.
            content: User message.
            current_file_path: Currently open file.
            selected_code: Selected code snippet.
            apply_changes: Whether to apply file modifications.

        Returns:
            ChatCompletionResponse with messages and applied changes.
        """
        project = await self._projects.ensure_owned(user_id, project_id)
        project_oid = parse_object_id(project_id, "project_id")
        session = await self._chat.get_or_create_session(
            project_oid,
            parse_object_id(user_id, "user_id"),
        )
        session_oid = parse_object_id(session["id"], "session_id")

        user_message = await self._chat.add_message(
            session_id=session_oid,
            project_id=project_oid,
            role="user",
            content=content,
        )

        files = await self._files.list_for_project(project_oid)
        folders = await self._folders.list_for_project(project_oid)
        history = await self._chat.recent_messages(session_oid, limit=20)
        recent = await self._cache.get(f"recent:file:{user_id}:{project_id}")
        recent_paths = [recent] if recent else []

        context = await self._context_builder.build(
            project=project,
            files=files,
            folders=folders,
            chat_history=history[:-1],
            current_file_path=current_file_path,
            selected_code=selected_code,
            recent_paths=recent_paths,
        )
        messages = self._prompt_builder.build(context, content)

        started = time.perf_counter()
        llm_response = await self._provider.complete(messages)
        latency_ms = int((time.perf_counter() - started) * 1000)
        parsed = self._parser.parse(llm_response.content)

        applied: List[FileChangeProposal] = []
        if apply_changes and parsed.file_changes:
            applied = await self._modifier.apply(project_id, parsed.file_changes)

        assistant_message = await self._chat.add_message(
            session_id=session_oid,
            project_id=project_oid,
            role="assistant",
            content=parsed.message,
            token_count=llm_response.total_tokens,
            model=llm_response.model,
            latency_ms=latency_ms,
            file_changes=[change.model_dump() for change in applied],
        )

        logger.info(
            "AI turn project=%s tokens=%s latency_ms=%s changes=%s",
            project_id,
            llm_response.total_tokens,
            latency_ms,
            len(applied),
        )
        return ChatCompletionResponse(
            user_message=ChatMessageResponse(**user_message),
            assistant_message=ChatMessageResponse(**assistant_message),
            applied_changes=applied,
            metadata={
                "prompt_version": self._prompt_builder.PROMPT_VERSION,
                "token_estimate_context": context.token_estimate,
                "model": llm_response.model,
                "latency_ms": latency_ms,
            },
        )
