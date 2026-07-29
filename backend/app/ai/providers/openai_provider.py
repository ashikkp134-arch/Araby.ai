"""OpenAI LLM provider implementation."""

import logging
from typing import AsyncIterator, List

from openai import AsyncOpenAI

from app.ai.providers.base import LLMMessage, LLMProvider, LLMResponse, StreamChunk
from app.core.config import get_settings
from app.utils.exceptions import AppException

logger = logging.getLogger(__name__)


def _is_placeholder_key(api_key: str) -> bool:
    """Return True when the key is clearly a template placeholder."""
    key = (api_key or "").strip()
    return not key or key.startswith("sk-your-") or key == "sk-your-openai-api-key"


def _classify_provider_error(exc: Exception) -> tuple[str, int, str]:
    """Map an OpenAI SDK error to (message, status_code, error_code).

    Args:
        exc: Exception raised by the SDK.

    Returns:
        Tuple of user-facing message, HTTP status, and machine error code.
    """
    status = getattr(exc, "status_code", None)
    body = getattr(exc, "body", None)
    code = None
    message = None
    if isinstance(body, dict):
        err = body.get("error") if isinstance(body.get("error"), dict) else body
        if isinstance(err, dict):
            message = err.get("message")
            code = err.get("code")
        elif isinstance(body.get("error"), str):
            message = body.get("error")
        elif body.get("message"):
            message = body.get("message")

    text = (message or str(exc) or "").lower()
    if (
        status == 401
        or code == "invalid_api_key"
        or "incorrect api key" in text
        or "invalid_api_key" in text
        or "authentication" in type(exc).__name__.lower()
    ):
        return (
            "AI authentication failed. Check OPENAI_API_KEY in backend/.env "
            "and restart the API server.",
            502,
            "llm_auth_error",
        )
    if status == 429 or "rate limit" in text:
        return (
            "AI provider rate limit reached. Please try again in a moment.",
            429,
            "llm_rate_limited",
        )
    if isinstance(message, str) and message.strip():
        return (f"AI provider request failed: {message.strip()}", 502, "llm_provider_error")
    raw = str(exc).strip()
    if raw:
        if " - " in raw:
            raw = raw.rsplit(" - ", 1)[-1]
        return (f"AI provider request failed: {raw}", 502, "llm_provider_error")
    return ("AI provider request failed", 502, "llm_provider_error")


def _raise_provider_error(exc: Exception) -> None:
    """Raise a normalized AppException for provider failures.

    Args:
        exc: Upstream SDK exception.

    Raises:
        AppException: Always.
    """
    detail, status_code, error_code = _classify_provider_error(exc)
    raise AppException(detail, status_code=status_code, error_code=error_code) from exc


class OpenAIProvider(LLMProvider):
    """OpenAI Chat Completions provider."""

    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        """Initialize the OpenAI provider.

        Args:
            api_key: Optional API key override.
            model: Optional model override.
        """
        settings = get_settings()
        self._api_key = api_key or settings.openai_api_key
        self._model = model or settings.openai_model
        if _is_placeholder_key(self._api_key):
            logger.warning(
                "OPENAI_API_KEY is missing or looks like a placeholder; AI chat will fail until set"
            )
        # A present-but-empty OPENAI_BASE_URL environment variable is read by
        # some OpenAI SDK releases as an empty URL instead of the default host.
        # Always provide a valid endpoint explicitly.
        base_url = (
            (settings.openai_base_url or "").strip()
            or "https://api.openai.com/v1"
        )
        self._client = AsyncOpenAI(
            api_key=self._api_key or "missing",
            base_url=base_url,
        )

    async def complete(
        self,
        messages: List[LLMMessage],
        temperature: float = 0.2,
        max_tokens: int = 4096,
        model: str | None = None,
    ) -> LLMResponse:
        """Generate a non-streaming OpenAI completion.

        Args:
            messages: Conversation messages.
            temperature: Sampling temperature.
            max_tokens: Maximum output tokens.
            model: Optional model override for this call.

        Returns:
            Normalized LLMResponse.

        Raises:
            AppException: When the OpenAI call fails.
        """
        if _is_placeholder_key(self._api_key):
            raise AppException(
                "OPENAI_API_KEY is not configured",
                status_code=503,
                error_code="llm_not_configured",
            )
        use_model = (model or self._model).strip()
        try:
            response = await self._client.chat.completions.create(
                model=use_model,
                messages=[{"role": m.role, "content": m.content} for m in messages],
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except Exception as exc:
            logger.exception("OpenAI completion failed")
            _raise_provider_error(exc)
        choice = response.choices[0].message.content or ""
        usage = response.usage
        return LLMResponse(
            content=choice,
            model=response.model,
            prompt_tokens=usage.prompt_tokens if usage else 0,
            completion_tokens=usage.completion_tokens if usage else 0,
            total_tokens=usage.total_tokens if usage else 0,
            raw=response.model_dump(),
        )

    async def stream(
        self,
        messages: List[LLMMessage],
        temperature: float = 0.2,
        max_tokens: int = 4096,
        model: str | None = None,
    ) -> AsyncIterator[StreamChunk]:
        """Stream an OpenAI completion including final usage when available.

        Args:
            messages: Conversation messages.
            temperature: Sampling temperature.
            max_tokens: Maximum output tokens.
            model: Optional model override for this call.

        Yields:
            Content deltas and a terminal usage chunk.
        """
        if _is_placeholder_key(self._api_key):
            raise AppException(
                "OPENAI_API_KEY is not configured",
                status_code=503,
                error_code="llm_not_configured",
            )
        use_model = (model or self._model).strip()
        try:
            stream = await self._client.chat.completions.create(
                model=use_model,
                messages=[{"role": m.role, "content": m.content} for m in messages],
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True,
                stream_options={"include_usage": True},
            )
        except Exception as exc:
            logger.exception("OpenAI stream failed")
            _raise_provider_error(exc)

        prompt_tokens = 0
        completion_tokens = 0
        total_tokens = 0
        reported_model = use_model
        saw_usage = False

        try:
            async for chunk in stream:
                if getattr(chunk, "model", None):
                    reported_model = chunk.model or reported_model
                usage = getattr(chunk, "usage", None)
                if usage is not None:
                    prompt_tokens = getattr(usage, "prompt_tokens", 0) or 0
                    completion_tokens = getattr(usage, "completion_tokens", 0) or 0
                    total_tokens = getattr(usage, "total_tokens", 0) or 0
                    saw_usage = True
                delta = None
                if chunk.choices:
                    delta = chunk.choices[0].delta.content
                if delta:
                    yield StreamChunk(content=delta, model=reported_model)
        except Exception as exc:
            logger.exception("OpenAI stream iteration failed")
            _raise_provider_error(exc)

        if saw_usage:
            yield StreamChunk(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                model=reported_model,
                has_usage=True,
            )
