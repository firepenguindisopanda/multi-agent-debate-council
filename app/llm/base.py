from typing import AsyncIterator, Literal, Protocol, TypedDict


class ChatMessage(TypedDict):
    role: Literal["system", "user", "assistant"]
    content: str


class LLMError(Exception):
    """A failure talking to the model provider, with a user-presentable message."""


class LLMClient(Protocol):
    def stream_chat(self, messages: list[ChatMessage], *, max_tokens: int) -> AsyncIterator[str]:
        """Yield text deltas for a chat completion."""
        ...
