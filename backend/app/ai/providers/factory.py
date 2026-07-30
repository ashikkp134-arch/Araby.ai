"""LLM provider factory."""

from app.ai.providers.base import LLMProvider
from app.ai.providers.openai_provider import OpenAIProvider
from app.ai.providers.stubs import (
    AnthropicProvider,
    AzureOpenAIProvider,
    GeminiProvider,
    OllamaProvider,
)
from app.core.config import get_settings
from app.utils.exceptions import ValidationAppError


def get_llm_provider(provider_name: str | None = None) -> LLMProvider:
    """Resolve an LLM provider by name.

    Args:
        provider_name: Optional provider override.

    Returns:
        Concrete LLMProvider instance.

    Raises:
        ValidationAppError: If the provider name is unknown.
    """
    settings = get_settings()
    name = (provider_name or settings.llm_provider).lower().strip()
    if name == "xai":
        return OpenAIProvider(
            api_key=settings.xai_api_key,
            model=settings.xai_model_coding,
            base_url=settings.xai_base_url,
        )
    mapping = {
        "openai": OpenAIProvider,
        "anthropic": AnthropicProvider,
        "gemini": GeminiProvider,
        "ollama": OllamaProvider,
        "azure_openai": AzureOpenAIProvider,
    }
    if name not in mapping:
        raise ValidationAppError(f"Unknown LLM provider: {name}")
    return mapping[name]()
