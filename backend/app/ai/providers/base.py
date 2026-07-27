"""Abstract LLM provider interface."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Dict, List, Optional


@dataclass
class LLMMessage:
    """Chat message sent to an LLM provider.

    Attributes:
        role: Message role (system/user/assistant).
        content: Message content.
    """

    role: str
    content: str


@dataclass
class LLMResponse:
    """Normalized LLM completion response.

    Attributes:
        content: Assistant text content.
        model: Model identifier.
        prompt_tokens: Prompt token count.
        completion_tokens: Completion token count.
        total_tokens: Total token count.
        raw: Provider-specific raw payload.
    """

    content: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    raw: Dict[str, Any] = field(default_factory=dict)


class LLMProvider(ABC):
    """Abstract provider interface for LLM backends."""

    @abstractmethod
    async def complete(
        self,
        messages: List[LLMMessage],
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        """Generate a non-streaming completion.

        Args:
            messages: Conversation messages.
            temperature: Sampling temperature.
            max_tokens: Maximum output tokens.

        Returns:
            Normalized LLMResponse.
        """

    @abstractmethod
    async def stream(
        self,
        messages: List[LLMMessage],
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> AsyncIterator[str]:
        """Generate a streaming completion.

        Args:
            messages: Conversation messages.
            temperature: Sampling temperature.
            max_tokens: Maximum output tokens.

        Yields:
            Content deltas as they arrive.
        """
