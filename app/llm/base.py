from dataclasses import dataclass
from typing import AsyncIterator, Literal, Protocol, TypedDict


class ChatMessage(TypedDict):
    role: Literal["system", "user", "assistant"]
    content: str


class LLMError(Exception):
    """A failure talking to the model provider, with a user-presentable message."""


@dataclass
class CallStats:
    """What one chat call cost and how it ended, filled in while it streams.

    Field names follow the OpenTelemetry GenAI conventions (gen_ai.usage.input_tokens,
    gen_ai.response.finish_reasons, gen_ai.response.time_to_first_chunk, ...).
    Timings cover the whole call, including any retries.
    """

    request_model: str | None = None
    response_model: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    finish_reason: str | None = None
    time_to_first_chunk_ms: int | None = None
    duration_ms: int | None = None
    retries: int = 0


class LLMClient(Protocol):
    def stream_chat(
        self, messages: list[ChatMessage], *, max_tokens: int, stats: CallStats | None = None
    ) -> AsyncIterator[str]:
        """Yield text deltas for a chat completion, recording metrics into `stats`."""
        ...
