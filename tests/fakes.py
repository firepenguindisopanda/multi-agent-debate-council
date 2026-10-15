import asyncio

from app.llm import CallStats, ChatMessage, LLMError

REPORT = """## Verdict
Ship an MVP.

## Agreed requirements
- Login works

## Open questions
- Who owns support? (Product Owner)

## Key risks
- Exam-season load spikes

## Recommended next steps
1. Write the user stories"""


class FakeLLM:
    """Scripted stand-in for the model provider, used only in tests."""

    model = "fake/scripted-model"

    def __init__(self, *, delay: float = 0.0, fail_after_calls: int | None = None):
        self.delay = delay
        self.fail_after_calls = fail_after_calls
        self.calls: list[list[ChatMessage]] = []

    async def stream_chat(
        self, messages: list[ChatMessage], *, max_tokens: int, stats: CallStats | None = None
    ):
        self.calls.append(messages)
        stats = stats if stats is not None else CallStats()
        stats.request_model = stats.response_model = self.model
        if self.fail_after_calls is not None and len(self.calls) > self.fail_after_calls:
            raise LLMError("NVIDIA NIM rate limit reached. Wait a moment and try again.")
        system = messages[0]["content"]
        text = (
            REPORT
            if "Moderator" in system
            else f"Reply #{len(self.calls)} with a **concrete** point."
        )
        words = text.split(" ")
        for i, word in enumerate(words):
            if self.delay:
                await asyncio.sleep(self.delay)
            if i == 0:
                stats.time_to_first_chunk_ms = 1
            yield word + " "
        # Stand-in token counts: one per word.
        stats.input_tokens = sum(len(m["content"].split()) for m in messages)
        stats.output_tokens = len(words)
        stats.finish_reason = "stop"
        stats.duration_ms = len(words)
