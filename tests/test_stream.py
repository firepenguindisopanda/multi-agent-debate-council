from starlette.requests import Request

from app.database import engine
from app.main import app
from app.services.debate_events import MessageCompleted, MessageStarted
from app.services.debate_runner import LiveState
from app.web.stream import _render_event
from tests.conftest import wait_for
from tests.test_debates import create


async def test_no_db_connections_held_while_a_debate_streams():
    from sqlmodel import Session

    from app.models import User
    from app.repositories.debate import AgentRepository, DebateRepository
    from app.services.debate_runner import DebateRunner
    from app.web.stream import debate_event_stream
    from tests.fakes import FakeLLM

    with Session(engine) as db:
        user = User(username="u", email="u@example.com", password="x", role="regular_user")
        db.add(user)
        db.commit()
        debate = DebateRepository(db).create(
            topic="A topic long enough",
            max_rounds=2,
            user_id=user.id,
            agents=AgentRepository(db).get_many([1, 2]),
        )
    runner = DebateRunner(llm=FakeLLM(delay=0.01))
    runner.start(debate.id)
    stream = debate_event_stream(_request(), debate.id, runner)
    try:
        for _ in range(6):  # snapshot plus a few live events
            await stream.__anext__()
            assert engine.pool.checkedout() == 0
    finally:
        await stream.aclose()
        await runner.shutdown()


def _request():
    return Request(
        {
            "type": "http",
            "app": app,
            "router": app.router,
            "method": "GET",
            "path": "/",
            "headers": [],
            "query_string": b"",
        }
    )


def test_new_message_card_renders_empty_so_queued_tokens_are_not_doubled(auth_client):
    debate_id = create(auth_client, agent_ids=(1, 2), rounds=1).json()["id"]
    data = wait_for(auth_client, debate_id)
    message_id = data["messages"][0]["id"]

    runner = app.state.runner
    runner._live[debate_id] = LiveState(message_id=message_id, message_text="already streamed")
    try:
        html = _render_event(MessageStarted(debate_id, message_id, 1), _request(), runner)
    finally:
        runner._live.pop(debate_id)
    assert f'id="msg-{message_id}-body"' in html
    assert "already streamed" not in html


def test_events_for_deleted_rows_render_nothing(auth_client):
    runner = app.state.runner
    assert _render_event(MessageCompleted(999, 1), _request(), runner) == ""
