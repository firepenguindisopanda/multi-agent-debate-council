"""Roll a debate's LLM calls up into the numbers worth looking at."""

from dataclasses import dataclass
from statistics import mean

from app.models import Debate, LLMCallKind


@dataclass(frozen=True)
class RunStats:
    calls: int
    failed_calls: int
    # None when the provider didn't report usage for every call.
    input_tokens: int | None
    output_tokens: int | None
    truncated_calls: int  # finish_reason == "length": cut off by max_tokens
    retries: int
    model_seconds: float  # summed call durations, including retries
    avg_turn_ttft_ms: int | None


def summarize(debate: Debate) -> RunStats | None:
    calls = list(debate.llm_calls)
    if not calls:
        return None
    usage_known = all(c.input_tokens is not None for c in calls if c.error is None)
    turn_ttfts = [
        c.time_to_first_chunk_ms
        for c in calls
        if c.kind == LLMCallKind.TURN and c.time_to_first_chunk_ms is not None
    ]
    return RunStats(
        calls=len(calls),
        failed_calls=sum(c.error is not None for c in calls),
        input_tokens=sum(c.input_tokens or 0 for c in calls) if usage_known else None,
        output_tokens=sum(c.output_tokens or 0 for c in calls) if usage_known else None,
        truncated_calls=sum(c.finish_reason == "length" for c in calls),
        retries=sum(c.retries for c in calls),
        model_seconds=round(sum(c.duration_ms or 0 for c in calls) / 1000, 1),
        avg_turn_ttft_ms=round(mean(turn_ttfts)) if turn_ttfts else None,
    )
