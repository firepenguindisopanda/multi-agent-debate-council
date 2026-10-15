"""One-off live check of the NVIDIA NIM setup (run via `python -m app.cli nim-check`)."""

from app.config import get_settings
from app.llm.base import CallStats, LLMError
from app.llm.nim import NIMClient

# Judges should come from a different family than the Llama generator to avoid
# self-preference; these name fragments pick out likely candidates.
JUDGE_FAMILIES = ("deepseek", "qwen", "mistral-large", "gpt-oss", "nemotron")


async def run_check(model: str | None, echo) -> bool:
    """Return True when the live call worked. `echo` prints a line."""
    s = get_settings()
    client = NIMClient(
        api_key=s.nvidia_api_key,
        base_url=s.nvidia_base_url,
        model=model or s.llm_model,
        temperature=0.0,
        top_p=1.0,
        timeout=s.llm_timeout_seconds,
        max_retries=s.llm_max_retries,
    )

    echo(f"Endpoint: {s.nvidia_base_url}")
    try:
        models = await client.list_models()
        candidates = [m for m in models if any(f in m.lower() for f in JUDGE_FAMILIES)]
        echo(f"Models listed: {len(models)}")
        echo(
            f"Configured model listed: {'yes' if client.model in models else 'NO'} ({client.model})"
        )
        echo("Judge candidates (non-Llama families, verify they respond before relying on one):")
        for m in candidates:
            echo(f"  - {m}")
    except LLMError as e:
        echo(f"Could not list models: {e}")

    stats = CallStats()
    text = ""
    try:
        async for delta in client.stream_chat(
            [{"role": "user", "content": "Reply with exactly: council ready"}],
            max_tokens=20,
            stats=stats,
        ):
            text += delta
    except LLMError as e:
        echo(f"Live call FAILED: {e}")
        return False

    echo(f"Live call OK: {text.strip()!r}")
    echo(f"  response model:      {stats.response_model}")
    echo(f"  finish reason:       {stats.finish_reason}")
    echo(f"  time to first token: {stats.time_to_first_chunk_ms} ms")
    echo(f"  duration:            {stats.duration_ms} ms (retries: {stats.retries})")
    if stats.input_tokens is not None:
        echo(f"  token usage:         {stats.input_tokens} in / {stats.output_tokens} out  ✓")
    elif not client.include_usage:
        echo("  token usage:         NIM rejected stream_options; token counts will be empty")
    else:
        echo("  token usage:         not reported; token counts will be empty")
    return True
