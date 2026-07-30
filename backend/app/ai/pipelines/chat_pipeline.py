"""End-to-end AI chat pipeline with routing, streaming, tracing, and guardrails."""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Dict, Iterator, List, Optional

from opentelemetry import trace

from app.ai.context.builder import ContextBuilder, ProjectContext
from app.ai.guardrails import (
    RESPONSIBLE_AI_MESSAGE,
    GuardResult,
    check_input,
    check_output,
    check_sensitive_data_request,
    message_fingerprint,
    sanitize_user_input,
)
from app.ai.pipelines.file_modifier import FileModifier
from app.ai.pipelines.image_discovery import ImageAssetResolver, ImageDiscoveryResult
from app.ai.pipelines.preview_integrity import (
    IntegrityIssue,
    build_exhausted_user_message,
    build_repair_prompt,
    find_asset_usage_issues,
    find_integrity_issues,
)
from app.ai.pipelines.response_parser import ResponseParser
from app.ai.prompts.builder import PromptBuilder
from app.ai.providers.base import LLMMessage, LLMProvider
from app.ai.providers.factory import get_llm_provider
from app.ai.routing import RequestCategory, RequestRouter, RoutingDecision
from app.core.config import get_settings
from app.core.redis import RedisCache
from app.core.telemetry import get_tracer, record_exception, set_span_attrs
from app.repositories.chat_repository import ChatRepository
from app.repositories.file_repository import FileRepository, FolderRepository
from app.schemas.chat import ChatCompletionResponse, ChatMessageResponse, FileChangeProposal
from app.services.file_service import FileService
from app.services.project_service import ProjectService
from app.utils.exceptions import AppException, ValidationAppError
from app.utils.object_id import parse_object_id
from app.utils.workspace_file_policy import edit_restriction_message

logger = logging.getLogger(__name__)
tracer = get_tracer("app.ai.pipeline")

# Lazy import to keep module import light when agentic builder is disabled.
def _get_website_builder_runner():
    from app.ai.agents.website_builder import WebsiteBuilderRunner

    return WebsiteBuilderRunner



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
    image_discovery: Optional[ImageDiscoveryResult] = None


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
        self._image_resolver = ImageAssetResolver()

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
                responsible_ai = self._responsible_ai_block(content)
                if responsible_ai is not None:
                    set_span_attrs(span, responsible_ai.to_metadata("responsible_ai"))
                    return await self._refuse_sensitive_turn(
                        user_id,
                        project_id,
                        content,
                        responsible_ai,
                    )
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

                    if self._should_use_agentic_website_builder(prepared):
                        done: Optional[StreamEvent] = None
                        async for event in self._stream_agentic_website(prepared):
                            if event.type == "done":
                                done = event
                            elif event.type == "error":
                                raise AppException(
                                    event.content or "Website builder failed",
                                    status_code=502,
                                    error_code="agentic_website_failed",
                                )
                        if done is None or not done.assistant_message:
                            raise AppException(
                                "Website builder produced no result",
                                status_code=502,
                                error_code="agentic_website_empty",
                            )
                        return ChatCompletionResponse(
                            user_message=ChatMessageResponse(**prepared.user_message),
                            assistant_message=ChatMessageResponse(**done.assistant_message),
                            applied_changes=done.file_changes,
                            metadata=done.metadata or {"agentic": True},
                        )

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
                    completion = await self._finalize_turn(
                        prepared=prepared,
                        raw_content=llm_response.content,
                        model=llm_response.model,
                        prompt_tokens=llm_response.prompt_tokens,
                        completion_tokens=llm_response.completion_tokens,
                        total_tokens=llm_response.total_tokens,
                        latency_ms=latency_ms,
                    )
                    return await self._apply_preview_repairs(
                        prepared=prepared,
                        completion=completion,
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
                responsible_ai = self._responsible_ai_block(content)
                if responsible_ai is not None:
                    set_span_attrs(span, responsible_ai.to_metadata("responsible_ai"))
                    refusal = await self._refuse_sensitive_turn(
                        user_id,
                        project_id,
                        content,
                        responsible_ai,
                    )
                    yield StreamEvent(type="start", metadata=refusal.metadata)
                    yield StreamEvent(
                        type="delta",
                        content=refusal.assistant_message.content,
                    )
                    yield StreamEvent(
                        type="done",
                        content=refusal.assistant_message.content,
                        metadata=refusal.metadata,
                        assistant_message=refusal.assistant_message.model_dump(mode="json"),
                        user_message=refusal.user_message.model_dump(mode="json"),
                    )
                    return
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

            if self._should_use_agentic_website_builder(prepared):
                async for event in self._stream_agentic_website(prepared):
                    yield event
                return

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
            async for event in self._stream_preview_repairs(prepared, completion):
                yield event

    def _responsible_ai_block(self, content: str) -> Optional[GuardResult]:
        """Return the guard result when a turn targets credentials or PII.

        Args:
            content: Raw user message.

        Returns:
            Blocking GuardResult, or None when the request may proceed.
        """
        if not get_settings().guardrails_enabled:
            return None
        result = check_sensitive_data_request(content)
        return None if result.allowed else result

    async def _refuse_sensitive_turn(
        self,
        user_id: str,
        project_id: str,
        content: str,
        guard: GuardResult,
    ) -> ChatCompletionResponse:
        """Persist a refusal turn for a credentials/PII request without an LLM call.

        Args:
            user_id: Authenticated user id.
            project_id: Project id.
            content: Raw user message.
            guard: Blocking guard result.

        Returns:
            ChatCompletionResponse holding the refusal and no file changes.
        """
        await self._projects.ensure_owned(user_id, project_id)
        project_oid = parse_object_id(project_id, "project_id")
        session = await self._chat.get_or_create_session(
            project_oid,
            parse_object_id(user_id, "user_id"),
        )
        session_oid = parse_object_id(session["id"], "session_id")
        refusal = guard.reason or RESPONSIBLE_AI_MESSAGE

        user_message = await self._chat.add_message(
            session_id=session_oid,
            project_id=project_oid,
            role="user",
            content=guard.sanitized_text or sanitize_user_input(content),
        )
        assistant_message = await self._chat.add_message(
            session_id=session_oid,
            project_id=project_oid,
            role="assistant",
            content=refusal,
        )
        logger.info("Responsible-AI refusal for project=%s", project_id)
        return ChatCompletionResponse(
            user_message=ChatMessageResponse(**user_message),
            assistant_message=ChatMessageResponse(**assistant_message),
            applied_changes=[],
            metadata=guard.to_metadata("responsible_ai"),
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
            return GuardResult(
                allowed=True,
                reason="guardrails_disabled",
                sanitized_text=sanitize_user_input(content),
            )
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
            # Prefer sanitized text for persistence, hashing, routing, and prompts.
            safe_content = (
                input_guard.sanitized_text
                if input_guard.sanitized_text is not None
                else content
            )
            msg_hash = message_fingerprint(safe_content)
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
                content=safe_content,
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
                    safe_content,
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
                    user_request=safe_content,
                )
                set_span_attrs(
                    ctx_span,
                    {
                        "context.token_estimate": context.token_estimate,
                        "context.files": len(context.relevant_files),
                    },
                )

            image_discovery: Optional[ImageDiscoveryResult] = None
            if workspace_type == "website" or routing.category == RequestCategory.WEBSITE_BUILDER:
                with tracer.start_as_current_span("ai.image_discovery") as img_span:
                    prior_user_requirements = [
                        str(item.get("content") or "")
                        for item in context.chat_history[-8:]
                        if str(item.get("role") or "").lower() == "user"
                    ]
                    semantic_context = "\n".join(prior_user_requirements)[-6000:]
                    image_discovery = await self._image_resolver.discover(
                        safe_content,
                        semantic_context=semantic_context,
                    )
                    set_span_attrs(
                        img_span,
                        {
                            "image.discovery.required": image_discovery.required,
                            "image.discovery.domain": image_discovery.domain,
                            "image.discovery.asset_roles": len(image_discovery.assets),
                            "image.discovery.url_count": image_discovery.url_count,
                            "image.discovery.providers": ",".join(
                                image_discovery.providers_used
                            ),
                        },
                    )

            with tracer.start_as_current_span("ai.prompt.build"):
                messages = self._prompt_builder.build(
                    context,
                    safe_content,
                    category=routing.category,
                    image_discovery=image_discovery,
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
                image_discovery=image_discovery,
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
                    RESPONSIBLE_AI_MESSAGE
                    if "secret_leak" in output_guard.labels
                    else (
                        "I couldn't apply those changes because the response failed "
                        "output safety checks. Please rephrase your request."
                    )
                )
                set_span_attrs(span, {"guardrail.output.blocked": True})
                logger.warning(
                    "Output guardrail blocked project=%s labels=%s",
                    prepared.project_id,
                    output_guard.labels,
                )
            elif prepared.apply_changes and parsed.file_changes:
                with tracer.start_as_current_span("ai.file_apply"):
                    workspace_type = str(prepared.project.get("workspace_type") or "")
                    try:
                        applied, reverse = await self._modifier.apply(
                            prepared.project_id,
                            parsed.file_changes,
                            workspace_type=workspace_type,
                        )
                        reverse_changes = [item.to_dict() for item in reverse]
                    except ValidationAppError as exc:
                        applied = []
                        reverse_changes = []
                        assistant_content = exc.message or edit_restriction_message(
                            workspace_type
                        )
                        set_span_attrs(
                            span,
                            {
                                "workspace.file_type.blocked": True,
                                "workspace.type": workspace_type,
                            },
                        )
                        logger.info(
                            "Workspace file-type policy blocked AI edits project=%s workspace=%s",
                            prepared.project_id,
                            workspace_type,
                        )

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
            if prepared.image_discovery is not None:
                metadata["image_discovery_required"] = prepared.image_discovery.required
                metadata["image_discovery_domain"] = prepared.image_discovery.domain
                metadata["image_discovery_roles"] = list(prepared.image_discovery.assets.keys())
                metadata["image_discovery_url_count"] = prepared.image_discovery.url_count
                metadata["image_discovery_providers"] = list(
                    prepared.image_discovery.providers_used
                )
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

    def _should_use_agentic_website_builder(self, prepared: PreparedTurn) -> bool:
        """Whether this turn should use the LangGraph multi-agent website builder.

        Agentic mode is for substantial website builds (avoids single-response
        truncation). Lightweight Q&A and tiny edits stay on the single-shot path.
        """
        settings = get_settings()
        if not bool(getattr(settings, "website_agentic_enabled", True)):
            return False
        workspace = str(prepared.project.get("workspace_type") or "").lower()
        if workspace != "website" and prepared.routing.category != RequestCategory.WEBSITE_BUILDER:
            return False
        if prepared.routing.tier.value == "light":
            return False
        text = ""
        # Prefer the sanitized content from the persisted user message.
        if prepared.user_message:
            text = str(prepared.user_message.get("content") or "")
        text_l = text.lower()
        build_hit = any(
            token in text_l
            for token in (
                "build",
                "create",
                "generate",
                "make",
                "scaffold",
                "landing",
                "website",
                "premium",
                "production-quality",
                "production quality",
            )
        )
        path_count = len(prepared.context.all_paths or [])
        if build_hit or len(text) > 350 or path_count < 6:
            return True
        return prepared.routing.category == RequestCategory.WEBSITE_BUILDER

    async def _stream_agentic_website(
        self,
        prepared: PreparedTurn,
    ) -> AsyncIterator[StreamEvent]:
        """Run the LangGraph website builder and persist the final assistant turn."""
        settings = get_settings()
        runner_cls = _get_website_builder_runner()
        runner = runner_cls(
            provider=self._provider,
            file_modifier=self._modifier,
            file_repo=self._files,
            image_resolver=self._image_resolver,
        )
        existing_paths = list(prepared.context.all_paths or [])
        collected_deltas: List[str] = []
        done_event: Optional[StreamEvent] = None
        started = time.perf_counter()

        async for event in runner.run_stream(
            project_id=prepared.project_id,
            user_request=str(prepared.user_message.get("content") or ""),
            project_name=str(prepared.project.get("name") or ""),
            workspace_type=str(prepared.project.get("workspace_type") or "website"),
            existing_paths=existing_paths,
            coding_model=prepared.routing.model,
            light_model=settings.openai_model_light or prepared.routing.model,
        ):
            if event.type == "delta" and event.content:
                collected_deltas.append(event.content)
                yield event
            elif event.type in {"preview_ready", "stage_done"}:
                # Forward mid-build UI signals so the frontend can open Live Preview
                # after Home and notify when background L2/L3 finish.
                yield event
            elif event.type == "start":
                yield StreamEvent(
                    type="start",
                    metadata={
                        "model": prepared.routing.model,
                        "category": prepared.routing.category.value,
                        "tier": prepared.routing.tier.value,
                        "agentic": True,
                        "builder": "langgraph_website",
                        **(event.metadata or {}),
                    },
                )
            elif event.type == "error":
                yield event
                return
            elif event.type == "done":
                done_event = event

        latency_ms = int((time.perf_counter() - started) * 1000)
        content = (done_event.content if done_event else "") or "".join(collected_deltas[-5:])
        if not content.strip():
            content = "Agentic website build completed."
        applied = list(done_event.file_changes if done_event else [])
        # Reverse changes aren't tracked across multi-stage applies yet; undo
        # still works for the latest single-shot turns. Store empty reverse set.
        assistant_message = await self._chat.add_message(
            session_id=prepared.session_oid,
            project_id=parse_object_id(prepared.project_id, "project_id"),
            role="assistant",
            content=content,
            token_count=None,
            model=prepared.routing.model,
            latency_ms=latency_ms,
            file_changes=[change.model_dump() for change in applied],
            reverse_changes=[],
        )
        metadata = {
            "prompt_version": self._prompt_builder.PROMPT_VERSION,
            "agentic": True,
            "builder": "langgraph_website",
            "model": prepared.routing.model,
            "latency_ms": latency_ms,
            "category": prepared.routing.category.value,
            "tier": prepared.routing.tier.value,
            "file_changes.applied": len(applied),
            **(done_event.metadata if done_event else {}),
        }
        yield StreamEvent(
            type="done",
            content=content,
            file_changes=applied,
            metadata=metadata,
            assistant_message=ChatMessageResponse(**assistant_message).model_dump(mode="json"),
            user_message=ChatMessageResponse(**prepared.user_message).model_dump(mode="json"),
        )

    def _should_check_preview_integrity(self, prepared: PreparedTurn) -> bool:
        """Whether this turn should run Live Preview import integrity checks."""
        if not prepared.apply_changes:
            return False
        workspace = str(prepared.project.get("workspace_type") or "").lower()
        if workspace == "website":
            return True
        return prepared.routing.category == RequestCategory.WEBSITE_BUILDER

    async def _load_integrity_issues(
        self,
        project_id: str,
        image_discovery: Optional[ImageDiscoveryResult] = None,
    ) -> List[IntegrityIssue]:
        """Load project files and return preview/content integrity issues."""
        project_oid = parse_object_id(project_id, "project_id")
        files = await self._files.list_for_project(project_oid)
        issues = find_integrity_issues(files)
        if image_discovery is not None and image_discovery.required:
            issues.extend(
                find_asset_usage_issues(
                    files,
                    image_discovery.assets,
                    asset_subjects=image_discovery.asset_subjects,
                )
            )
        return issues

    async def _apply_preview_repairs(
        self,
        *,
        prepared: PreparedTurn,
        completion: ChatCompletionResponse,
    ) -> ChatCompletionResponse:
        """Non-streaming wrapper: repair missing imports then return completion."""
        events: List[StreamEvent] = []
        async for event in self._stream_preview_repairs(prepared, completion):
            events.append(event)
        done = next((event for event in reversed(events) if event.type == "done"), None)
        if done is None:
            return completion
        metadata = dict(completion.metadata)
        metadata.update(done.metadata or {})
        return ChatCompletionResponse(
            user_message=completion.user_message,
            assistant_message=ChatMessageResponse(**(done.assistant_message or completion.assistant_message.model_dump(mode="json"))),
            applied_changes=done.file_changes or completion.applied_changes,
            metadata=metadata,
        )

    async def _stream_preview_repairs(
        self,
        prepared: PreparedTurn,
        completion: ChatCompletionResponse,
    ) -> AsyncIterator[StreamEvent]:
        """Validate Live Preview imports and auto-repair up to N times.

        Yields progress deltas during repairs, then a final ``done`` event that
        merges original + repair file changes. When retries are exhausted,
        appends guidance asking the user for a more specific prompt.
        """
        settings = get_settings()
        max_retries = max(0, int(settings.preview_repair_max_retries))
        all_changes = list(completion.applied_changes)
        metadata = dict(completion.metadata)
        assistant_content = completion.assistant_message.content
        assistant_payload = completion.assistant_message.model_dump(mode="json")

        if not self._should_check_preview_integrity(prepared) or max_retries == 0:
            yield StreamEvent(
                type="done",
                content=assistant_content,
                file_changes=all_changes,
                metadata=metadata,
                assistant_message=assistant_payload,
                user_message=completion.user_message.model_dump(mode="json"),
            )
            return

        # Only auto-repair when this turn changed files (avoid surprise LLM calls
        # on pure Q&A in a website project).
        if not all_changes:
            yield StreamEvent(
                type="done",
                content=assistant_content,
                file_changes=all_changes,
                metadata=metadata,
                assistant_message=assistant_payload,
                user_message=completion.user_message.model_dump(mode="json"),
            )
            return

        issues = await self._load_integrity_issues(
            prepared.project_id,
            prepared.image_discovery,
        )
        if not issues:
            metadata["preview_integrity"] = "ok"
            yield StreamEvent(
                type="done",
                content=assistant_content,
                file_changes=all_changes,
                metadata=metadata,
                assistant_message=assistant_payload,
                user_message=completion.user_message.model_dump(mode="json"),
            )
            return

        with tracer.start_as_current_span("ai.preview_repair") as span:
            set_span_attrs(
                span,
                {
                    "preview.integrity.issues": len(issues),
                    "preview.repair.max_retries": max_retries,
                },
            )
            attempts_used = 0
            for attempt in range(1, max_retries + 1):
                attempts_used = attempt
                progress = (
                    f"\n\nAuto-repairing Live Preview blockers "
                    f"(attempt {attempt}/{max_retries})…\n"
                    f"Found {len(issues)} integrity issue(s).\n"
                )
                yield StreamEvent(type="delta", content=progress)
                assistant_content = f"{assistant_content}{progress}".strip()

                project_oid = parse_object_id(prepared.project_id, "project_id")
                files = await self._files.list_for_project(project_oid)
                folders = await self._folders.list_for_project(project_oid)
                file_paths = [str(item.get("path") or "") for item in files]
                repair_user_prompt = build_repair_prompt(
                    issues,
                    attempt=attempt,
                    max_attempts=max_retries,
                    file_paths=file_paths,
                )
                context = await self._context_builder.build(
                    project=prepared.project,
                    files=files,
                    folders=folders,
                    chat_history=[],
                    current_file_path=None,
                    selected_code=None,
                    recent_paths=file_paths[:12],
                    open_tabs=[],
                    user_request=repair_user_prompt,
                )
                repair_messages = self._prompt_builder.build(
                    context,
                    repair_user_prompt,
                    category=RequestCategory.WEBSITE_BUILDER,
                    image_discovery=prepared.image_discovery,
                )

                try:
                    with tracer.start_as_current_span("ai.preview_repair.llm") as llm_span:
                        llm_response = await self._provider.complete(
                            repair_messages,
                            temperature=min(prepared.routing.temperature, 0.3),
                            max_tokens=prepared.routing.max_tokens,
                            model=prepared.routing.model,
                        )
                        set_span_attrs(
                            llm_span,
                            {
                                "llm.prompt_tokens": llm_response.prompt_tokens,
                                "llm.completion_tokens": llm_response.completion_tokens,
                                "attempt": attempt,
                            },
                        )
                except Exception as exc:
                    logger.exception("Preview repair LLM call failed attempt=%s", attempt)
                    record_exception(span, exc)
                    break

                parsed = self._parser.parse(llm_response.content)
                applied: List[FileChangeProposal] = []
                reverse_changes: List[Dict[str, Any]] = []
                if prepared.apply_changes and parsed.file_changes:
                    workspace_type = str(prepared.project.get("workspace_type") or "")
                    try:
                        applied, reverse = await self._modifier.apply(
                            prepared.project_id,
                            parsed.file_changes,
                            workspace_type=workspace_type,
                        )
                        reverse_changes = [item.to_dict() for item in reverse]
                        all_changes.extend(applied)
                    except ValidationAppError as exc:
                        applied = []
                        reverse_changes = []
                        note = exc.message or edit_restriction_message(workspace_type)
                        repair_message = await self._chat.add_message(
                            session_id=prepared.session_oid,
                            project_id=project_oid,
                            role="assistant",
                            content=note,
                        )
                        assistant_payload = ChatMessageResponse(**repair_message).model_dump(
                            mode="json"
                        )
                        assistant_content = f"{assistant_content}\n\n{note}".strip()
                        yield StreamEvent(type="delta", content=f"{note}\n")
                        break

                note = parsed.message.strip() or (
                    f"Auto-repair attempt {attempt}/{max_retries}: "
                    f"applied {len(applied)} file change(s)."
                )
                repair_message = await self._chat.add_message(
                    session_id=prepared.session_oid,
                    project_id=project_oid,
                    role="assistant",
                    content=note,
                    token_count=(
                        (llm_response.prompt_tokens or 0)
                        + (llm_response.completion_tokens or 0)
                    )
                    or None,
                    model=llm_response.model or prepared.routing.model,
                    latency_ms=None,
                    file_changes=[change.model_dump() for change in applied],
                    reverse_changes=reverse_changes,
                )
                assistant_payload = ChatMessageResponse(**repair_message).model_dump(mode="json")
                assistant_content = f"{assistant_content}\n\n{note}".strip()
                yield StreamEvent(type="delta", content=f"{note}\n")

                issues = await self._load_integrity_issues(
                    prepared.project_id,
                    prepared.image_discovery,
                )
                if not issues:
                    metadata["preview_integrity"] = "repaired"
                    metadata["preview_repair_attempts"] = attempts_used
                    set_span_attrs(span, {"preview.repair.success": True, "attempt": attempt})
                    break

            if issues:
                guidance = build_exhausted_user_message(issues)
                exhausted = await self._chat.add_message(
                    session_id=prepared.session_oid,
                    project_id=parse_object_id(prepared.project_id, "project_id"),
                    role="assistant",
                    content=guidance,
                )
                assistant_payload = ChatMessageResponse(**exhausted).model_dump(mode="json")
                assistant_content = f"{assistant_content}\n\n{guidance}".strip()
                metadata["preview_integrity"] = "failed"
                metadata["preview_repair_attempts"] = attempts_used
                metadata["preview_integrity_issues"] = len(issues)
                set_span_attrs(
                    span,
                    {
                        "preview.repair.success": False,
                        "preview.integrity.remaining": len(issues),
                    },
                )
                yield StreamEvent(type="delta", content=f"\n{guidance}\n")

            yield StreamEvent(
                type="done",
                content=assistant_content,
                file_changes=all_changes,
                metadata=metadata,
                assistant_message=assistant_payload,
                user_message=completion.user_message.model_dump(mode="json"),
            )
