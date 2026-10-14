"""NVIDIA NIM client. NIM exposes an OpenAI-compatible API, so we use the openai SDK."""

import logging
from typing import AsyncIterator

import openai
from openai import AsyncOpenAI

from app.llm.base import ChatMessage, LLMError

logger = logging.getLogger(__name__)


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
    ):
        self.model = model
        self.temperature = temperature
        self.top_p = top_p
        self._client = (
            AsyncOpenAI(api_key=api_key, base_url=base_url, timeout=timeout, max_retries=2)
            if api_key
            else None
        )

    async def stream_chat(
        self, messages: list[ChatMessage], *, max_tokens: int
    ) -> AsyncIterator[str]:
        if self._client is None:
            raise LLMError("NVIDIA_API_KEY is not set. Add it to your .env file and restart.")
        try:
            stream = await self._client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=self.temperature,
                top_p=self.top_p,
                max_tokens=max_tokens,
                stream=True,
            )
            async for chunk in stream:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta.content
                if delta:
                    yield delta
        except openai.AuthenticationError as e:
            raise LLMError("NVIDIA NIM rejected the API key (401). Check NVIDIA_API_KEY.") from e
        except openai.NotFoundError as e:
            raise LLMError(
                f"Model '{self.model}' was not found on NVIDIA NIM. Check LLM_MODEL."
            ) from e
        except openai.RateLimitError as e:
            raise LLMError("NVIDIA NIM rate limit reached. Wait a moment and try again.") from e
        except openai.APITimeoutError as e:
            raise LLMError("NVIDIA NIM timed out.") from e
        except openai.APIConnectionError as e:
            raise LLMError("Could not reach NVIDIA NIM. Check your network connection.") from e
        except openai.APIStatusError as e:
            logger.warning("NIM error %s: %s", e.status_code, e.message)
            raise LLMError(f"NVIDIA NIM returned an error ({e.status_code}).") from e
