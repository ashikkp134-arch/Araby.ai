"""End-to-end AI chat pipeline with routing, streaming, tracing, and guardrails."""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Dict, Iterator, List, Optional

from opentelemetry import trace

from app.ai.context.builder import ContextBuilder, ProjectContext
from app.ai.guardrails import GuardResult, check_input, check_output, message_fingerprint
from app.ai.pipelines.file_modifier import FileModifier
from app.ai.pipelines.response_parser import ResponseParser
from app.ai.prompts.builder import PromptBuilder
from app.ai.providers.base import LLMMessage, LLMProvider
from app.ai.providers.factory import get_llm_provider
from app.ai.routing import RequestRouter, RoutingDecision
from app.core.config import get_settings
from app.core.redis import RedisCache
from app.core.telemetry import get_tracer, record_exception, set_span_attrs
from app.repositories.chat_repository import ChatRepository
from app.repositories.file_repository import FileRepository, FolderRepository
from app.schemas.chat import ChatCompletionResponse, ChatMessageResponse, FileChangeProposal
from app.services.file_service import FileService
from app.services.project_service import ProjectService
from app.utils.exceptions import AppException
from app.utils.object_id import parse_object_id

logger = logging.getLogger(__name__)
tracer = get_tracer("app.ai.pipeline")


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
        input_guard: Input guardrail result.
        message_hash: Fingerprint of user content.
    """

    project: Dict[str, Any]
    project_id: str
    session_oid: Any
    user_message: Dict[str, Any]
    context: ProjectContext
    messages: List[LLMMessage]
    routing: RoutingDecision
    apply_changes: bool = True
    input_guard: Optional[GuardResult] = None
    message_hash: str = ""


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


@contextmanager
def _session_context(session_id: str, metadata: Dict[str, Any]) -> Iterator[None]:
    """Attach session metadata to the active span without nested generator CMs.

    OpenInference ``using_session`` / ``using_attributes`` are generator-based
    context managers; nesting them around streaming LLM calls can raise
    ``RuntimeError: generator didn't stop after throw()`` when the provider
    fails. Span attributes are safer and still show up in Phoenix.

    Args:
        session_id: Chat session id.
        metadata: Extra span metadata.

    Yields:
        None.
    """
    span = trace.get_current_span()
    attrs: Dict[str, Any] = {"session.id": session_id}
    for key, value in metadata.items():
        attrs[f"meta.{key}"] = value
    set_span_attrs(span, attrs)
    yield


def _user_facing_stream_error(exc: BaseException) -> str:
    """Convert provider/pipeline exceptions into a safe UI message.

    Args:
        exc: Raised exception.

    Returns:
        Short user-facing error string.
    """
    if isinstance(exc, AppException):
        message = exc.message
        if exc.error_code == "llm_auth_error":
            return (
                "AI authentication failed. Check OPENAI_API_KEY in backend/.env "
                "and restart the API server."
            )
        if exc.error_code == "llm_not_configured":
            return "AI is not configured. Set OPENAI_API_KEY in backend/.env and restart."
        if exc.error_code == "input_blocked":
            return message
    else:
        message = str(exc) or "Stream failed"

    # Unwrap chained exceptions (e.g. RuntimeError wrapping AppException).
    cause = getattr(exc, "__cause__", None) or getattr(exc, "__context__", None)
    if cause is not None and cause is not exc:
        nested = _user_facing_stream_error(cause)
        if nested and "generator didn't stop" not in nested.lower():
            if "generator didn't stop" in message.lower() or "RuntimeError" in type(exc).__name__:
                return nested

    lowered = message.lower()
    if (
        "incorrect api key" in lowered
        or "invalid_api_key" in lowered
        or "authentication" in lowered
        or "401" in lowered
    ):
        return (
            "AI authentication failed. Check OPENAI_API_KEY in backend/.env "
            "and restart the API server."
        )
    if "rate limit" in lowered or "429" in lowered:
        return "AI provider rate limit reached. Please try again in a moment."
    if "generator didn't stop" in lowered:
        return "AI request failed. Please try again."
    if len(message) > 280:
        return message[:277] + "..."
    return message


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
        with tracer.start_as_current_span("ai.chat.turn") as span:
            set_span_attrs(
                span,
                {
                    "user.id": user_id,
                    "project.id": project_id,
                    "input.chars": len(content or ""),
                    "input.hash": message_fingerprint(content or ""),
                    "stream": False,
                },
            )
            try:
                prepared = await self._prepare_turn(
                    user_id=user_id,
                    project_id=project_id,
                    content=content,
                    current_file_path=current_file_path,
                    selected_code=selected_code,
                    apply_changes=apply_changes,
                    open_tabs=open_tabs,
                )
                session_id = str(prepared.session_oid)
                meta = {
                    "user_id": user_id,
                    "project_id": project_id,
                    "category": prepared.routing.category.value,
                    "tier": prepared.routing.tier.value,
                }
                ctx = _session_context(session_id, meta)
                with ctx:
                    set_span_attrs(
                        span,
                        {
                            "session.id": session_id,
                            "llm.model": prepared.routing.model,
                            "routing.category": prepared.routing.category.value,
                            "routing.tier": prepared.routing.tier.value,
                            "context.token_estimate": prepared.context.token_estimate,
                            "llm.max_tokens": prepared.routing.max_tokens,
                        },
                    )
                    if prepared.input_guard:
                        set_span_attrs(span, prepared.input_guard.to_metadata("input"))

                    started = time.perf_counter()
                    with tracer.start_as_current_span("ai.llm.complete") as llm_span:
                        llm_response = await self._provider.complete(
                            prepared.messages,
                            temperature=prepared.routing.temperature,
                            max_tokens=prepared.routing.max_tokens,
                            model=prepared.routing.model,
                        )
                        set_span_attrs(
                            llm_span,
                            {
                                "llm.prompt_tokens": llm_response.prompt_tokens,
                                "llm.completion_tokens": llm_response.completion_tokens,
                                "llm.total_tokens": llm_response.total_tokens,
                                "llm.model": llm_response.model,
                            },
                        )
                    latency_ms = int((time.perf_counter() - started) * 1000)
                    set_span_attrs(
                        span,
                        {
                            "llm.prompt_tokens": llm_response.prompt_tokens,
                            "llm.completion_tokens": llm_response.completion_tokens,
                            "llm.total_tokens": llm_response.total_tokens,
                            "latency_ms": latency_ms,
                        },
                    )
                    return await self._finalize_turn(
                        prepared=prepared,
                        raw_content=llm_response.content,
                        model=llm_response.model,
                        prompt_tokens=llm_response.prompt_tokens,
                        completion_tokens=llm_response.completion_tokens,
                        total_tokens=llm_response.total_tokens,
                        latency_ms=latency_ms,
                    )
            except Exception as exc:
                record_exception(span, exc)
                raise

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
        with tracer.start_as_current_span("ai.chat.turn.stream") as span:
            set_span_attrs(
                span,
                {
                    "user.id": user_id,
                    "project.id": project_id,
                    "input.chars": len(content or ""),
                    "input.hash": message_fingerprint(content or ""),
                    "stream": True,
                },
            )
            try:
                prepared = await self._prepare_turn(
                    user_id=user_id,
                    project_id=project_id,
                    content=content,
                    current_file_path=current_file_path,
                    selected_code=selected_code,
                    apply_changes=apply_changes,
                    open_tabs=open_tabs,
                )
            except Exception as exc:
                record_exception(span, exc)
                yield StreamEvent(type="error", content=_user_facing_stream_error(exc))
                return

            session_id = str(prepared.session_oid)
            meta = {
                "user_id": user_id,
                "project_id": project_id,
                "category": prepared.routing.category.value,
                "tier": prepared.routing.tier.value,
            }
            set_span_attrs(
                span,
                {
                    "session.id": session_id,
                    "llm.model": prepared.routing.model,
                    "routing.category": prepared.routing.category.value,
                    "routing.tier": prepared.routing.tier.value,
                    "context.token_estimate": prepared.context.token_estimate,
                    "llm.max_tokens": prepared.routing.max_tokens,
                },
            )
            if prepared.input_guard:
                set_span_attrs(span, prepared.input_guard.to_metadata("input"))

            yield StreamEvent(
                type="start",
                metadata={
                    "model": prepared.routing.model,
                    "category": prepared.routing.category.value,
                    "tier": prepared.routing.tier.value,
                    "context_token_estimate": prepared.context.token_estimate,
                    **(prepared.input_guard.to_metadata("input") if prepared.input_guard else {}),
                },
            )

            chunks: List[str] = []
            prompt_tokens = 0
            completion_tokens = 0
            total_tokens = 0
            model = prepared.routing.model
            started = time.perf_counter()
            try:
                with _session_context(session_id, meta):
                    with tracer.start_as_current_span("ai.llm.stream") as llm_span:
                        async for part in self._provider.stream(
                            prepared.messages,
                            temperature=prepared.routing.temperature,
                            max_tokens=prepared.routing.max_tokens,
                            model=prepared.routing.model,
                        ):
                            if part.content:
                                chunks.append(part.content)
                                yield StreamEvent(type="delta", content=part.content)
                            if part.has_usage:
                                prompt_tokens = part.prompt_tokens
                                completion_tokens = part.completion_tokens
                                total_tokens = part.total_tokens
                                if part.model:
                                    model = part.model
                        set_span_attrs(
                            llm_span,
                            {
                                "llm.prompt_tokens": prompt_tokens,
                                "llm.completion_tokens": completion_tokens,
                                "llm.total_tokens": total_tokens,
                                "llm.model": model,
                            },
                        )
            except Exception as exc:
                logger.exception("Streaming AI turn failed")
                record_exception(span, exc)
                yield StreamEvent(type="error", content=_user_facing_stream_error(exc))
                return

            latency_ms = int((time.perf_counter() - started) * 1000)
            set_span_attrs(
                span,
                {
                    "llm.prompt_tokens": prompt_tokens,
                    "llm.completion_tokens": completion_tokens,
                    "llm.total_tokens": total_tokens,
                    "latency_ms": latency_ms,
                },
            )
            raw = "".join(chunks)
            completion = await self._finalize_turn(
                prepared=prepared,
                raw_content=raw,
                model=model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
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

    def _run_input_guard(self, content: str) -> GuardResult:
        """Evaluate input guardrails according to settings.

        Args:
            content: User message.

        Returns:
            GuardResult.

        Raises:
            AppException: When input is blocked.
        """
        settings = get_settings()
        if not settings.guardrails_enabled:
            return GuardResult(allowed=True, reason="guardrails_disabled")
        result = check_input(content)
        if not result.allowed and settings.guardrails_block_on_input:
            raise AppException(
                result.reason or "Request blocked by input safety policy",
                status_code=400,
                error_code="input_blocked",
                details=result.to_metadata("input"),
            )
        return result

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
        with tracer.start_as_current_span("ai.prepare_turn") as span:
            input_guard = self._run_input_guard(content)
            msg_hash = message_fingerprint(content)
            set_span_attrs(
                span,
                {
                    "input.hash": msg_hash,
                    **input_guard.to_metadata("input"),
                },
            )

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
            with tracer.start_as_current_span("ai.route"):
                routing = self._router.classify(
                    content,
                    workspace_type,
                    has_selection=bool(selected_code),
                    open_tab_count=len(tabs),
                )

            with tracer.start_as_current_span("ai.context.build") as ctx_span:
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
                set_span_attrs(
                    ctx_span,
                    {
                        "context.token_estimate": context.token_estimate,
                        "context.files": len(context.relevant_files),
                    },
                )

            with tracer.start_as_current_span("ai.prompt.build"):
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
                input_guard=input_guard,
                message_hash=msg_hash,
            )

    async def _finalize_turn(
        self,
        *,
        prepared: PreparedTurn,
        raw_content: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        total_tokens: int,
        latency_ms: int,
    ) -> ChatCompletionResponse:
        """Parse, apply file changes, and persist the assistant message.

        Args:
            prepared: Prepared turn state.
            raw_content: Full assistant text.
            model: Model id used.
            prompt_tokens: Prompt token usage.
            completion_tokens: Completion token usage.
            total_tokens: Total token usage when known.
            latency_ms: Latency in milliseconds.

        Returns:
            ChatCompletionResponse.
        """
        settings = get_settings()
        with tracer.start_as_current_span("ai.finalize_turn") as span:
            with tracer.start_as_current_span("ai.parse"):
                parsed = self._parser.parse(raw_content)

            output_guard = GuardResult(allowed=True, reason="guardrails_disabled")
            if settings.guardrails_enabled:
                output_guard = check_output(raw_content, parsed.file_changes)
            set_span_attrs(span, output_guard.to_metadata("output"))

            applied: List[FileChangeProposal] = []
            reverse_changes: List[Dict[str, Any]] = []
            assistant_content = parsed.message
            if (
                settings.guardrails_enabled
                and not output_guard.allowed
                and settings.guardrails_block_on_output
            ):
                assistant_content = (
                    "I couldn't apply those changes because the response failed "
                    "output safety checks. Please rephrase your request."
                )
                set_span_attrs(span, {"guardrail.output.blocked": True})
                logger.warning(
                    "Output guardrail blocked project=%s labels=%s",
                    prepared.project_id,
                    output_guard.labels,
                )
            elif prepared.apply_changes and parsed.file_changes:
                with tracer.start_as_current_span("ai.file_apply"):
                    applied, reverse = await self._modifier.apply(
                        prepared.project_id,
                        parsed.file_changes,
                    )
                    reverse_changes = [item.to_dict() for item in reverse]

            tokens_for_store = total_tokens or (prompt_tokens + completion_tokens) or None
            assistant_message = await self._chat.add_message(
                session_id=prepared.session_oid,
                project_id=parse_object_id(prepared.project_id, "project_id"),
                role="assistant",
                content=assistant_content,
                token_count=tokens_for_store,
                model=model,
                latency_ms=latency_ms,
                file_changes=[change.model_dump() for change in applied],
                reverse_changes=reverse_changes,
            )

            logger.info(
                "AI turn project=%s category=%s tier=%s model=%s "
                "prompt_tokens=%s completion_tokens=%s total_tokens=%s "
                "context_tokens=%s latency_ms=%s changes=%s",
                prepared.project_id,
                prepared.routing.category.value,
                prepared.routing.tier.value,
                model,
                prompt_tokens,
                completion_tokens,
                total_tokens,
                prepared.context.token_estimate,
                latency_ms,
                len(applied),
            )
            metadata: Dict[str, Any] = {
                "prompt_version": self._prompt_builder.PROMPT_VERSION,
                "token_estimate_context": prepared.context.token_estimate,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
                "model": model,
                "latency_ms": latency_ms,
                "category": prepared.routing.category.value,
                "tier": prepared.routing.tier.value,
                "routing_reason": prepared.routing.reason,
                "input_hash": prepared.message_hash,
            }
            if prepared.input_guard:
                metadata.update(prepared.input_guard.to_metadata("input"))
            metadata.update(output_guard.to_metadata("output"))
            set_span_attrs(
                span,
                {
                    "llm.prompt_tokens": prompt_tokens,
                    "llm.completion_tokens": completion_tokens,
                    "llm.total_tokens": total_tokens,
                    "file_changes.applied": len(applied),
                },
            )
            return ChatCompletionResponse(
                user_message=ChatMessageResponse(**prepared.user_message),
                assistant_message=ChatMessageResponse(**assistant_message),
                applied_changes=applied,
                metadata=metadata,
            )
