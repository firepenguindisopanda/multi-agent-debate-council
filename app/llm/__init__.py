from functools import lru_cache

from app.config import get_settings
from app.llm.base import CallStats, ChatMessage, LLMClient, LLMError
from app.llm.nim import NIMClient


@lru_cache
def get_llm_client() -> LLMClient:
    s = get_settings()
    return NIMClient(
        api_key=s.nvidia_api_key,
        base_url=s.nvidia_base_url,
        model=s.llm_model,
        temperature=s.llm_temperature,
        top_p=s.llm_top_p,
        timeout=s.llm_timeout_seconds,
        max_retries=s.llm_max_retries,
    )


__all__ = ["CallStats", "ChatMessage", "LLMClient", "LLMError", "NIMClient", "get_llm_client"]
