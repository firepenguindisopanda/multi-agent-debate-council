"""NIMClient against a mocked HTTP transport (no network)."""

import json

import httpx
import pytest
from openai import AsyncOpenAI

from app.llm import CallStats, LLMError, NIMClient

BASE_URL = "https://integrate.api.nvidia.com/v1"
MODEL = "meta/llama-3.3-70b-instruct"


@pytest.fixture(autouse=True)
def no_backoff_sleep(monkeypatch):
    async def instant(_seconds):
        return None

    monkeypatch.setattr("app.llm.nim.asyncio.sleep", instant)


def make_client(handler) -> tuple[NIMClient, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    client = NIMClient(
        api_key="nvapi-test", base_url=BASE_URL, model=MODEL, temperature=0.5, top_p=0.9, timeout=5
    )
    client._client = AsyncOpenAI(
        api_key="nvapi-test",
        base_url=BASE_URL,
        max_retries=0,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(record)),
    )
    return client, seen


def chunk(content=None, finish=None, usage=None, choices=True) -> dict:
    data = {"id": "c1", "object": "chat.completion.chunk", "created": 0, "model": MODEL}
    data["choices"] = (
        [{"index": 0, "delta": {"content": content}, "finish_reason": finish}] if choices else []
    )
    if usage:
        data["usage"] = usage
    return data


def sse(*chunks: dict) -> httpx.Response:
    body = "".join(f"data: {json.dumps(c)}\n\n" for c in chunks) + "data: [DONE]\n\n"
    return httpx.Response(200, content=body.encode(), headers={"content-type": "text/event-stream"})


def ok_stream(_request=None) -> httpx.Response:
    return sse(
        chunk("Hello"),
        chunk(", council", finish="stop"),
        # Final usage chunk: empty choices, as the OpenAI API sends it.
        chunk(
            choices=False, usage={"prompt_tokens": 42, "completion_tokens": 7, "total_tokens": 49}
        ),
    )


async def collect(client: NIMClient, stats: CallStats | None = None) -> str:
    out = ""
    async for delta in client.stream_chat(
        [{"role": "user", "content": "hi"}], max_tokens=50, stats=stats
    ):
        out += delta
    return out


async def test_streams_text_and_records_usage_and_finish_reason():
    client, seen = make_client(ok_stream)
    stats = CallStats()
    assert await collect(client, stats) == "Hello, council"

    body = json.loads(seen[0].content)
    assert str(seen[0].url) == f"{BASE_URL}/chat/completions"
    assert seen[0].headers["authorization"] == "Bearer nvapi-test"
    assert body["model"] == MODEL and body["stream"] is True and body["max_tokens"] == 50
    assert body["stream_options"] == {"include_usage": True}

    assert (stats.input_tokens, stats.output_tokens) == (42, 7)
    assert stats.finish_reason == "stop"
    assert stats.request_model == stats.response_model == MODEL
    assert stats.time_to_first_chunk_ms is not None and stats.duration_ms is not None
    assert stats.retries == 0


async def test_length_stop_is_recorded_as_truncation():
    client, _ = make_client(lambda r: sse(chunk("cut off mid", finish="length")))
    stats = CallStats()
    await collect(client, stats)
    assert stats.finish_reason == "length"
    assert stats.input_tokens is None  # no usage chunk sent


async def test_retries_rate_limit_and_counts_it():
    responses = iter([httpx.Response(429, json={"error": {"message": "slow down"}}), ok_stream()])
    client, seen = make_client(lambda r: next(responses))
    stats = CallStats()
    assert await collect(client, stats) == "Hello, council"
    assert stats.retries == 1 and len(seen) == 2


async def test_gives_up_after_max_retries():
    client, seen = make_client(lambda r: httpx.Response(429, json={"error": {"message": "x"}}))
    stats = CallStats()
    with pytest.raises(LLMError, match="rate limit"):
        await collect(client, stats)
    assert stats.retries == 2 and len(seen) == 3


async def test_falls_back_when_stream_options_is_rejected():
    def handler(request):
        if "stream_options" in json.loads(request.content):
            return httpx.Response(400, json={"error": {"message": "stream_options not supported"}})
        return ok_stream()

    client, seen = make_client(handler)
    stats = CallStats()
    assert await collect(client, stats) == "Hello, council"
    assert client.include_usage is False and stats.retries == 0
    assert "stream_options" not in json.loads(seen[-1].content)
    await collect(client)  # later calls skip the option straight away
    assert len(seen) == 3


async def test_does_not_retry_once_text_has_streamed():
    async def dropped_mid_stream():
        yield f"data: {json.dumps(chunk('partial'))}\n\n".encode()
        raise httpx.ReadError("connection dropped")

    client, seen = make_client(
        lambda r: httpx.Response(
            200, content=dropped_mid_stream(), headers={"content-type": "text/event-stream"}
        )
    )
    received, stats = [], CallStats()
    with pytest.raises(LLMError, match="Could not reach"):
        async for delta in client.stream_chat(
            [{"role": "user", "content": "hi"}], max_tokens=50, stats=stats
        ):
            received.append(delta)
    assert received == ["partial"]  # not duplicated by a retry
    assert len(seen) == 1 and stats.retries == 0


@pytest.mark.parametrize(
    ("status", "message"),
    [(401, "rejected the API key"), (404, "was not found"), (429, "rate limit"), (500, r"\(500\)")],
)
async def test_maps_http_errors_to_friendly_messages(status, message):
    client, _ = make_client(lambda r: httpx.Response(status, json={"error": {"message": "x"}}))
    with pytest.raises(LLMError, match=message):
        await collect(client)


async def test_missing_api_key_fails_clearly():
    client = NIMClient(
        api_key=None, base_url=BASE_URL, model="m", temperature=0.5, top_p=0.9, timeout=5
    )
    with pytest.raises(LLMError, match="NVIDIA_API_KEY is not set"):
        await collect(client)


async def test_nim_check_reports_usage_and_judge_candidates(monkeypatch):
    from app.llm import check

    def handler(request):
        if request.url.path.endswith("/models"):
            ids = [MODEL, "deepseek-ai/deepseek-v3.2", "qwen/qwen3-235b", "meta/llama-3.1-8b"]
            return httpx.Response(
                200, json={"object": "list", "data": [{"id": i, "object": "model"} for i in ids]}
            )
        return ok_stream()

    def fake_client(**kwargs):
        client, _ = make_client(handler)
        client.model = kwargs["model"]
        return client

    monkeypatch.setattr(check, "NIMClient", fake_client)
    monkeypatch.setattr(check.get_settings(), "nvidia_api_key", "nvapi-test")
    lines: list[str] = []
    assert await check.run_check(None, lines.append) is True
    out = "\n".join(lines)
    assert "Models listed: 4" in out and "Configured model listed: yes" in out
    assert "deepseek-ai/deepseek-v3.2" in out and "qwen/qwen3-235b" in out
    assert "meta/llama-3.1-8b" not in out  # same family as the generator
    assert "42 in / 7 out" in out
