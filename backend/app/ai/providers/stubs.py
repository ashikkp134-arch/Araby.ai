"""Stub providers for future multi-vendor support."""

from typing import AsyncIterator, List

from app.ai.providers.base import LLMMessage, LLMProvider, LLMResponse
from app.utils.exceptions import AppException


class AnthropicProvider(LLMProvider):
    """Placeholder Anthropic provider."""

    async def complete(
        self,
        messages: List[LLMMessage],
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        """Raise until Anthropic is configured.

        Args:
            messages: Unused messages.
            temperature: Unused temperature.
            max_tokens: Unused max tokens.

        Raises:
            AppException: Always, until implemented.
        """
        raise AppException(
            "Anthropic provider is not configured",
            status_code=501,
            error_code="provider_not_implemented",
        )

    async def stream(
        self,
        messages: List[LLMMessage],
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> AsyncIterator[str]:
        """Raise until Anthropic streaming is configured."""
        raise AppException(
            "Anthropic provider is not configured",
            status_code=501,
            error_code="provider_not_implemented",
        )
        yield ""  # pragma: no cover


class GeminiProvider(LLMProvider):
    """Placeholder Gemini provider."""

    async def complete(
        self,
        messages: List[LLMMessage],
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        """Raise until Gemini is configured."""
        raise AppException(
            "Gemini provider is not configured",
            status_code=501,
            error_code="provider_not_implemented",
        )

    async def stream(
        self,
        messages: List[LLMMessage],
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> AsyncIterator[str]:
        """Raise until Gemini streaming is configured."""
        raise AppException(
            "Gemini provider is not configured",
            status_code=501,
            error_code="provider_not_implemented",
        )
        yield ""  # pragma: no cover


class OllamaProvider(LLMProvider):
    """Placeholder Ollama provider."""

    async def complete(
        self,
        messages: List[LLMMessage],
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        """Raise until Ollama is configured."""
        raise AppException(
            "Ollama provider is not configured",
            status_code=501,
            error_code="provider_not_implemented",
        )

    async def stream(
        self,
        messages: List[LLMMessage],
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> AsyncIterator[str]:
        """Raise until Ollama streaming is configured."""
        raise AppException(
            "Ollama provider is not configured",
            status_code=501,
            error_code="provider_not_implemented",
        )
        yield ""  # pragma: no cover


class AzureOpenAIProvider(LLMProvider):
    """Placeholder Azure OpenAI provider."""

    async def complete(
        self,
        messages: List[LLMMessage],
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        """Raise until Azure OpenAI is configured."""
        raise AppException(
            "Azure OpenAI provider is not configured",
            status_code=501,
            error_code="provider_not_implemented",
        )

    async def stream(
        self,
        messages: List[LLMMessage],
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> AsyncIterator[str]:
        """Raise until Azure OpenAI streaming is configured."""
        raise AppException(
            "Azure OpenAI provider is not configured",
            status_code=501,
            error_code="provider_not_implemented",
        )
        yield ""  # pragma: no cover
