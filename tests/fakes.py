import asyncio

from app.llm import ChatMessage, LLMError


class FakeLLM:
    """Scripted stand-in for the model provider, used only in tests."""

    def __init__(self, *, delay: float = 0.0, fail_after_calls: int | None = None):
        self.delay = delay
        self.fail_after_calls = fail_after_calls
        self.calls: list[list[ChatMessage]] = []

    async def stream_chat(self, messages: list[ChatMessage], *, max_tokens: int):
        self.calls.append(messages)
        if self.fail_after_calls is not None and len(self.calls) > self.fail_after_calls:
            raise LLMError("NVIDIA NIM rate limit reached. Wait a moment and try again.")
        system = messages[0]["content"]
        if "Moderator" in system:
            text = "## Verdict\nShip an MVP.\n\n## Agreed requirements\n- Login works"
        else:
            text = f"Reply #{len(self.calls)} with a **concrete** point."
        for word in text.split(" "):
            if self.delay:
                await asyncio.sleep(self.delay)
            yield word + " "
