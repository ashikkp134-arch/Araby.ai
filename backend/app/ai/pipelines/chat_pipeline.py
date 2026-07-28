"""End-to-end AI chat pipeline with routing and streaming."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Dict, List, Optional

from app.ai.context.builder import ContextBuilder, ProjectContext
from app.ai.pipelines.file_modifier import FileModifier
from app.ai.pipelines.response_parser import ResponseParser
from app.ai.prompts.builder import PromptBuilder
from app.ai.providers.base import LLMMessage, LLMProvider, LLMResponse
from app.ai.providers.factory import get_llm_provider
from app.ai.routing import RequestRouter, RoutingDecision
from app.core.redis import RedisCache
from app.repositories.chat_repository import ChatRepository
from app.repositories.file_repository import FileRepository, FolderRepository
from app.schemas.chat import ChatCompletionResponse, ChatMessageResponse, FileChangeProposal
from app.services.file_service import FileService
from app.services.project_service import ProjectService
from app.utils.object_id import parse_object_id

logger = logging.getLogger(__name__)


@dataclass
class PreparedTurn:
    """Shared state for a chat turn before LLM inference.

    Attributes:
        project: Owned project document.
        project_id: Project id string.
        session_oid: Chat session ObjectId-compatible id holder.
        user_message: Persisted user message dict.
        context: Built project context.
        messages: LLM messages.
        routing: Model/prompt routing decision.
        apply_changes: Whether to apply file ops.
    """

    project: Dict[str, Any]
    project_id: str
    session_oid: Any
    user_message: Dict[str, Any]
    context: ProjectContext
    messages: List[LLMMessage]
    routing: RoutingDecision
    apply_changes: bool = True


@dataclass
class StreamEvent:
    """Streaming event emitted by AIPipeline.run_stream.

    Attributes:
        type: start | delta | done | error.
        content: Text payload for delta/done/error.
        file_changes: Applied file changes on done.
        metadata: Telemetry on done.
        assistant_message: Persisted assistant message on done.
        user_message: Persisted user message on done.
    """

    type: str
    content: str = ""
    file_changes: List[FileChangeProposal] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    assistant_message: Optional[Dict[str, Any]] = None
    user_message: Optional[Dict[str, Any]] = None


class AIPipeline:
    """Orchestrate routing, context, prompts, LLM, parse, and file modify."""

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
        self._router = RequestRouter()

    async def run(
        self,
        user_id: str,
        project_id: str,
        content: str,
        current_file_path: Optional[str] = None,
        selected_code: Optional[str] = None,
        apply_changes: bool = True,
        open_tabs: Optional[List[str]] = None,
    ) -> ChatCompletionResponse:
        """Execute a full non-streaming AI chat turn.

        Args:
            user_id: Authenticated user id.
            project_id: Target project id.
            content: User message.
            current_file_path: Currently open file.
            selected_code: Selected code snippet.
            apply_changes: Whether to apply file modifications.
            open_tabs: Open editor tab paths.

        Returns:
            ChatCompletionResponse with messages and applied changes.
        """
        prepared = await self._prepare_turn(
            user_id=user_id,
            project_id=project_id,
            content=content,
            current_file_path=current_file_path,
            selected_code=selected_code,
            apply_changes=apply_changes,
            open_tabs=open_tabs,
        )
        started = time.perf_counter()
        llm_response = await self._provider.complete(
            prepared.messages,
            temperature=prepared.routing.temperature,
            max_tokens=prepared.routing.max_tokens,
            model=prepared.routing.model,
        )
        latency_ms = int((time.perf_counter() - started) * 1000)
        return await self._finalize_turn(
            prepared=prepared,
            raw_content=llm_response.content,
            model=llm_response.model,
            total_tokens=llm_response.total_tokens,
            latency_ms=latency_ms,
        )

    async def run_stream(
        self,
        user_id: str,
        project_id: str,
        content: str,
        current_file_path: Optional[str] = None,
        selected_code: Optional[str] = None,
        apply_changes: bool = True,
        open_tabs: Optional[List[str]] = None,
    ) -> AsyncIterator[StreamEvent]:
        """Execute a streaming AI chat turn with file-apply on completion.

        Args:
            user_id: Authenticated user id.
            project_id: Target project id.
            content: User message.
            current_file_path: Currently open file.
            selected_code: Selected code snippet.
            apply_changes: Whether to apply file modifications.
            open_tabs: Open editor tab paths.

        Yields:
            StreamEvent start/delta/done (or error).
        """
        prepared = await self._prepare_turn(
            user_id=user_id,
            project_id=project_id,
            content=content,
            current_file_path=current_file_path,
            selected_code=selected_code,
            apply_changes=apply_changes,
            open_tabs=open_tabs,
        )
        yield StreamEvent(
            type="start",
            metadata={
                "model": prepared.routing.model,
                "category": prepared.routing.category.value,
                "tier": prepared.routing.tier.value,
            },
        )
        chunks: List[str] = []
        started = time.perf_counter()
        try:
            async for delta in self._provider.stream(
                prepared.messages,
                temperature=prepared.routing.temperature,
                max_tokens=prepared.routing.max_tokens,
                model=prepared.routing.model,
            ):
                chunks.append(delta)
                yield StreamEvent(type="delta", content=delta)
        except Exception as exc:
            logger.exception("Streaming AI turn failed")
            yield StreamEvent(type="error", content=str(exc) or "Stream failed")
            return

        latency_ms = int((time.perf_counter() - started) * 1000)
        raw = "".join(chunks)
        completion = await self._finalize_turn(
            prepared=prepared,
            raw_content=raw,
            model=prepared.routing.model,
            total_tokens=0,
            latency_ms=latency_ms,
        )
        yield StreamEvent(
            type="done",
            content=completion.assistant_message.content,
            file_changes=completion.applied_changes,
            metadata=completion.metadata,
            assistant_message=completion.assistant_message.model_dump(mode="json"),
            user_message=completion.user_message.model_dump(mode="json"),
        )

    async def _prepare_turn(
        self,
        user_id: str,
        project_id: str,
        content: str,
        current_file_path: Optional[str],
        selected_code: Optional[str],
        apply_changes: bool,
        open_tabs: Optional[List[str]],
    ) -> PreparedTurn:
        """Persist the user message and assemble prompts/context/routing.

        Args:
            user_id: Authenticated user id.
            project_id: Project id.
            content: User message.
            current_file_path: Open file path.
            selected_code: Selection snippet.
            apply_changes: Apply file ops flag.
            open_tabs: Open tabs.

        Returns:
            PreparedTurn ready for inference.
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
        tabs = [p for p in (open_tabs or []) if p]

        workspace_type = str(project.get("workspace_type") or "javascript")
        routing = self._router.classify(
            content,
            workspace_type,
            has_selection=bool(selected_code),
            open_tab_count=len(tabs),
        )

        context = await self._context_builder.build(
            project=project,
            files=files,
            folders=folders,
            chat_history=history[:-1],
            current_file_path=current_file_path,
            selected_code=selected_code,
            recent_paths=recent_paths,
            open_tabs=tabs,
        )
        messages = self._prompt_builder.build(
            context,
            content,
            category=routing.category,
        )
        return PreparedTurn(
            project=project,
            project_id=project_id,
            session_oid=session_oid,
            user_message=user_message,
            context=context,
            messages=messages,
            routing=routing,
            apply_changes=apply_changes,
        )

    async def _finalize_turn(
        self,
        *,
        prepared: PreparedTurn,
        raw_content: str,
        model: str,
        total_tokens: int,
        latency_ms: int,
    ) -> ChatCompletionResponse:
        """Parse, apply file changes, and persist the assistant message.

        Args:
            prepared: Prepared turn state.
            raw_content: Full assistant text.
            model: Model id used.
            total_tokens: Token usage when known.
            latency_ms: Latency in milliseconds.

        Returns:
            ChatCompletionResponse.
        """
        parsed = self._parser.parse(raw_content)
        applied: List[FileChangeProposal] = []
        if prepared.apply_changes and parsed.file_changes:
            applied = await self._modifier.apply(prepared.project_id, parsed.file_changes)

        assistant_message = await self._chat.add_message(
            session_id=prepared.session_oid,
            project_id=parse_object_id(prepared.project_id, "project_id"),
            role="assistant",
            content=parsed.message,
            token_count=total_tokens or None,
            model=model,
            latency_ms=latency_ms,
            file_changes=[change.model_dump() for change in applied],
        )

        logger.info(
            "AI turn project=%s category=%s tier=%s model=%s tokens=%s latency_ms=%s changes=%s",
            prepared.project_id,
            prepared.routing.category.value,
            prepared.routing.tier.value,
            model,
            total_tokens,
            latency_ms,
            len(applied),
        )
        return ChatCompletionResponse(
            user_message=ChatMessageResponse(**prepared.user_message),
            assistant_message=ChatMessageResponse(**assistant_message),
            applied_changes=applied,
            metadata={
                "prompt_version": self._prompt_builder.PROMPT_VERSION,
                "token_estimate_context": prepared.context.token_estimate,
                "model": model,
                "latency_ms": latency_ms,
                "category": prepared.routing.category.value,
                "tier": prepared.routing.tier.value,
                "routing_reason": prepared.routing.reason,
            },
        )
