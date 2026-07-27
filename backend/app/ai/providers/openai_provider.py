"""OpenAI LLM provider implementation."""

import logging
from typing import AsyncIterator, List

from openai import AsyncOpenAI

from app.ai.providers.base import LLMMessage, LLMProvider, LLMResponse
from app.core.config import get_settings
from app.utils.exceptions import AppException

logger = logging.getLogger(__name__)


def _provider_error_detail(exc: Exception) -> str:
    """Build a user-facing message from an OpenAI-compatible API error.

    Args:
        exc: Exception raised by the SDK.

    Returns:
        Short human-readable failure reason.
    """
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        message = body.get("error") or body.get("message")
        if isinstance(message, dict):
            message = message.get("message")
        if message:
            return f"AI provider request failed: {message}"
    message = str(exc).strip()
    if message:
        # Prefer the trailing JSON/error fragment when present.
        if " - " in message:
            message = message.rsplit(" - ", 1)[-1]
        return f"AI provider request failed: {message}"
    return "AI provider request failed"


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
        if not self._api_key:
            logger.warning("OPENAI_API_KEY is not configured")
        # Empty OPENAI_BASE_URL keeps the default OpenAI host; set it for
        # OpenAI-compatible providers (e.g. Grok/xAI: https://api.x.ai/v1).
        base_url = (settings.openai_base_url or "").strip() or None
        self._client = AsyncOpenAI(
            api_key=self._api_key or "missing",
            base_url=base_url,
        )

    async def complete(
        self,
        messages: List[LLMMessage],
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        """Generate a non-streaming OpenAI completion.

        Args:
            messages: Conversation messages.
            temperature: Sampling temperature.
            max_tokens: Maximum output tokens.

        Returns:
            Normalized LLMResponse.

        Raises:
            AppException: When the OpenAI call fails.
        """
        if not self._api_key:
            raise AppException(
                "OPENAI_API_KEY is not configured",
                status_code=503,
                error_code="llm_not_configured",
            )
        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=[{"role": m.role, "content": m.content} for m in messages],
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except Exception as exc:
            logger.exception("OpenAI completion failed")
            detail = _provider_error_detail(exc)
            raise AppException(
                detail,
                status_code=502,
                error_code="llm_provider_error",
            ) from exc
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
    ) -> AsyncIterator[str]:
        """Stream an OpenAI completion.

        Args:
            messages: Conversation messages.
            temperature: Sampling temperature.
            max_tokens: Maximum output tokens.

        Yields:
            Content deltas.
        """
        if not self._api_key:
            raise AppException(
                "OPENAI_API_KEY is not configured",
                status_code=503,
                error_code="llm_not_configured",
            )
        stream = await self._client.chat.completions.create(
            model=self._model,
            messages=[{"role": m.role, "content": m.content} for m in messages],
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta.content if chunk.choices else None
            if delta:
                yield delta
