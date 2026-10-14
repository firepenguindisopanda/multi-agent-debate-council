"""NIMClient against a mocked HTTP transport (no network)."""

import json

import httpx
import pytest
from openai import AsyncOpenAI

from app.llm import LLMError, NIMClient

BASE_URL = "https://integrate.api.nvidia.com/v1"


def make_client(handler) -> tuple[NIMClient, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    client = NIMClient(
        api_key="nvapi-test",
        base_url=BASE_URL,
        model="meta/llama-3.3-70b-instruct",
        temperature=0.5,
        top_p=0.9,
        timeout=5,
    )
    client._client = AsyncOpenAI(
        api_key="nvapi-test",
        base_url=BASE_URL,
        max_retries=0,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(record)),
    )
    return client, seen


def sse_body(*deltas: str) -> bytes:
    chunks = [
        {
            "id": "c1",
            "object": "chat.completion.chunk",
            "created": 0,
            "model": "meta/llama-3.3-70b-instruct",
            "choices": [{"index": 0, "delta": {"content": d}, "finish_reason": None}],
        }
        for d in deltas
    ]
    lines = [f"data: {json.dumps(c)}\n\n" for c in chunks] + ["data: [DONE]\n\n"]
    return "".join(lines).encode()


async def collect(client: NIMClient) -> str:
    out = ""
    async for delta in client.stream_chat([{"role": "user", "content": "hi"}], max_tokens=50):
        out += delta
    return out


async def test_streams_deltas_with_expected_request():
    client, seen = make_client(
        lambda r: httpx.Response(
            200,
            content=sse_body("Hello", ", council"),
            headers={"content-type": "text/event-stream"},
        )
    )
    assert await collect(client) == "Hello, council"

    request = seen[0]
    assert str(request.url) == f"{BASE_URL}/chat/completions"
    assert request.headers["authorization"] == "Bearer nvapi-test"
    body = json.loads(request.content)
    assert body["model"] == "meta/llama-3.3-70b-instruct"
    assert body["stream"] is True and body["max_tokens"] == 50


@pytest.mark.parametrize(
    ("status", "message"),
    [(401, "rejected the API key"), (404, "was not found"), (429, "rate limit"), (500, "(500)")],
)
async def test_maps_http_errors_to_friendly_messages(status, message):
    client, _ = make_client(lambda r: httpx.Response(status, json={"error": {"message": "x"}}))
    with pytest.raises(LLMError, match=message.replace("(", r"\(").replace(")", r"\)")):
        await collect(client)


async def test_missing_api_key_fails_clearly():
    client = NIMClient(
        api_key=None, base_url=BASE_URL, model="m", temperature=0.5, top_p=0.9, timeout=5
    )
    with pytest.raises(LLMError, match="NVIDIA_API_KEY is not set"):
        await collect(client)
