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


@dataclass
class StreamChunk:
    """Streaming chunk from an LLM provider.

    Attributes:
        content: Text delta (empty for usage-only final chunk).
        prompt_tokens: Prompt tokens when usage is known.
        completion_tokens: Completion tokens when usage is known.
        total_tokens: Total tokens when usage is known.
        model: Model id when reported.
        has_usage: Whether token fields were populated.
    """

    content: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    model: str = ""
    has_usage: bool = False


class LLMProvider(ABC):
    """Abstract provider interface for LLM backends."""

    @abstractmethod
    async def complete(
        self,
        messages: List[LLMMessage],
        temperature: float = 0.2,
        max_tokens: int = 4096,
        model: Optional[str] = None,
    ) -> LLMResponse:
        """Generate a non-streaming completion.

        Args:
            messages: Conversation messages.
            temperature: Sampling temperature.
            max_tokens: Maximum output tokens.
            model: Optional model override for this call.

        Returns:
            Normalized LLMResponse.
        """

    @abstractmethod
    async def stream(
        self,
        messages: List[LLMMessage],
        temperature: float = 0.2,
        max_tokens: int = 4096,
        model: Optional[str] = None,
    ) -> AsyncIterator[StreamChunk]:
        """Generate a streaming completion.

        Args:
            messages: Conversation messages.
            temperature: Sampling temperature.
            max_tokens: Maximum output tokens.
            model: Optional model override for this call.

        Yields:
            StreamChunk text deltas and a final usage chunk when available.
        """
