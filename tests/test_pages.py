from tests.conftest import wait_for
from tests.test_debates import create


def test_public_pages_render(client):
    for path in ("/", "/login", "/register"):
        assert client.get(path).status_code == 200
    assert "Business Analyst" in client.get("/").text


def test_app_pages_render(auth_client):
    for path in ("/debates", "/debates/new", "/debates/list?q=x&status=completed"):
        assert auth_client.get(path).status_code == 200


def test_htmx_create_returns_redirect_or_inline_error(auth_client):
    headers = {"HX-Request": "true"}
    r = auth_client.post(
        "/debates", data={"topic": "too short", "agent_ids": ["1", "2"]}, headers=headers
    )
    assert r.status_code == 422 and 'class="alert alert-danger"' in r.text

    r = auth_client.post(
        "/debates",
        data={
            "topic": "A notification service for food delivery",
            "agent_ids": ["1", "2"],
            "max_rounds": "1",
        },
        headers=headers,
    )
    assert r.status_code == 204 and r.headers["HX-Redirect"].endswith("/debates/1")


def test_live_stream_ends_with_done_and_final_render(auth_client, fake_llm):
    fake_llm.delay = 0.005
    debate_id = create(auth_client, rounds=1).json()["id"]
    with auth_client.stream("GET", f"/debates/{debate_id}/events") as stream:
        body = "".join(stream.iter_text())
    events = [line[7:] for line in body.splitlines() if line.startswith("event: ")]
    assert events[-1] == "done" and events.count("update") >= 10
    assert 'hx-swap-oob="beforeend:#msg-1-body"' in body  # streamed tokens
    assert 'hx-swap-oob="beforeend:#summary-stream"' in body
    assert "<h2>Verdict</h2>" in body  # final render of the report


def test_completed_page_shows_report_and_rendered_markdown(auth_client):
    debate_id = create(auth_client, rounds=1).json()["id"]
    wait_for(auth_client, debate_id)
    page = auth_client.get(f"/debates/{debate_id}").text
    assert "sse-connect" not in page  # no live stream for finished debates
    assert "<strong>concrete</strong>" in page and "<h2>Verdict</h2>" in page


def test_model_output_is_escaped(auth_client, fake_llm):
    async def evil(messages, *, max_tokens, stats=None):
        yield "<script>alert(1)</script> [x](javascript:alert(1))"

    fake_llm.stream_chat = evil
    debate_id = create(auth_client, rounds=1).json()["id"]
    wait_for(auth_client, debate_id)
    page = auth_client.get(f"/debates/{debate_id}").text
    assert "<script>alert(1)</script>" not in page
    assert 'href="javascript:' not in page


def test_export_markdown(auth_client):
    debate_id = create(auth_client, rounds=1).json()["id"]
    wait_for(auth_client, debate_id)
    r = auth_client.get(f"/debates/{debate_id}/export.md")
    assert r.headers["content-type"].startswith("text/markdown")
    assert "## Council report" in r.text and "### Round 1" in r.text
