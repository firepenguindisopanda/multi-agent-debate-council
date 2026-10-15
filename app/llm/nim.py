"""NVIDIA NIM client. NIM exposes an OpenAI-compatible API, so we use the openai SDK."""

import asyncio
import logging
import random
import time
from typing import AsyncIterator

import openai
from openai import AsyncOpenAI

from app.llm.base import CallStats, ChatMessage, LLMError

logger = logging.getLogger(__name__)

# Worth retrying: the request never produced output and may succeed later.
RETRYABLE = (
    openai.RateLimitError,
    openai.APITimeoutError,
    openai.APIConnectionError,
    openai.InternalServerError,
)
MAX_BACKOFF_SECONDS = 20.0


def _elapsed_ms(start: float) -> int:
    return int((time.perf_counter() - start) * 1000)


def _backoff_seconds(attempt: int, error: Exception) -> float:
    """Honour Retry-After when the server sends one; otherwise exponential with jitter."""
    response = getattr(error, "response", None)
    retry_after = response.headers.get("retry-after") if response is not None else None
    if retry_after:
        try:
            return min(float(retry_after), MAX_BACKOFF_SECONDS)
        except ValueError:
            pass
    return min(2 ** (attempt - 1), MAX_BACKOFF_SECONDS) + random.uniform(0, 0.5)


class NIMClient:
    def __init__(
        self,
        *,
        api_key: str | None,
        base_url: str,
        model: str,
        temperature: float,
        top_p: float,
        timeout: float,
        max_retries: int = 2,
    ):
        self.model = model
        self.temperature = temperature
        self.top_p = top_p
        self.max_retries = max_retries
        # NVIDIA doesn't document stream_options; turned off if the API ever rejects it.
        self.include_usage = True
        # Retries happen here rather than in the SDK so they can be counted.
        self._client = (
            AsyncOpenAI(api_key=api_key, base_url=base_url, timeout=timeout, max_retries=0)
            if api_key
            else None
        )

    async def stream_chat(
        self, messages: list[ChatMessage], *, max_tokens: int, stats: CallStats | None = None
    ) -> AsyncIterator[str]:
        if self._client is None:
            raise LLMError("NVIDIA_API_KEY is not set. Add it to your .env file and restart.")
        stats = stats if stats is not None else CallStats()
        stats.request_model = self.model
        start = time.perf_counter()
        attempt = 0
        while True:
            produced_output = False
            try:
                extra = {"stream_options": {"include_usage": True}} if self.include_usage else {}
                stream = await self._client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=self.temperature,
                    top_p=self.top_p,
                    max_tokens=max_tokens,
                    stream=True,
                    **extra,
                )
                async for chunk in stream:
                    stats.response_model = chunk.model or stats.response_model
                    # The usage chunk comes last and has no choices, so read it before skipping.
                    if chunk.usage is not None:
                        stats.input_tokens = chunk.usage.prompt_tokens
                        stats.output_tokens = chunk.usage.completion_tokens
                    if not chunk.choices:
                        continue
                    choice = chunk.choices[0]
                    if choice.finish_reason:
                        stats.finish_reason = choice.finish_reason
                    if choice.delta.content:
                        if not produced_output:
                            stats.time_to_first_chunk_ms = _elapsed_ms(start)
                            produced_output = True
                        yield choice.delta.content
                stats.duration_ms = _elapsed_ms(start)
                return
            except openai.BadRequestError as e:
                if self.include_usage and "stream_options" in str(e).lower():
                    logger.warning("NIM rejected stream_options; continuing without token usage")
                    self.include_usage = False
                    continue
                raise self._error(e) from e
            except RETRYABLE as e:
                # Never retry once text has streamed: the caller would see it twice.
                if produced_output or attempt >= self.max_retries:
                    stats.duration_ms = _elapsed_ms(start)
                    raise self._error(e) from e
                attempt += 1
                stats.retries = attempt
                delay = _backoff_seconds(attempt, e)
                logger.info("NIM %s; retry %d in %.1fs", type(e).__name__, attempt, delay)
                await asyncio.sleep(delay)
            except openai.APIError as e:
                stats.duration_ms = _elapsed_ms(start)
                raise self._error(e) from e

    async def list_models(self) -> list[str]:
        """IDs of the models the API currently lists for this key."""
        if self._client is None:
            raise LLMError("NVIDIA_API_KEY is not set. Add it to your .env file and restart.")
        try:
            page = await self._client.models.list()
        except openai.APIError as e:
            raise self._error(e) from e
        return sorted(m.id for m in page.data)

    def _error(self, e: openai.APIError) -> LLMError:
        if isinstance(e, openai.AuthenticationError):
            return LLMError("NVIDIA NIM rejected the API key (401). Check NVIDIA_API_KEY.")
        if isinstance(e, openai.NotFoundError):
            return LLMError(f"Model '{self.model}' was not found on NVIDIA NIM. Check LLM_MODEL.")
        if isinstance(e, openai.RateLimitError):
            return LLMError("NVIDIA NIM rate limit reached. Wait a moment and try again.")
        if isinstance(e, openai.APITimeoutError):
            return LLMError("NVIDIA NIM timed out.")
        if isinstance(e, openai.APIConnectionError):
            return LLMError("Could not reach NVIDIA NIM. Check your network connection.")
        if isinstance(e, openai.APIStatusError):
            logger.warning("NIM error %s: %s", e.status_code, e.message)
            return LLMError(f"NVIDIA NIM returned an error ({e.status_code}).")
        return LLMError("NVIDIA NIM request failed.")
