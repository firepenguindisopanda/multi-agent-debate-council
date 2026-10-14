from app.main import app
from app.services.debate_runner import DebateRunner
from tests.conftest import register_and_login, wait_for

TOPIC = "A booking system for university study rooms"


def create(client, agent_ids=(1, 2, 3), rounds=2, topic=TOPIC):
    return client.post(
        "/api/debates", json={"topic": topic, "agent_ids": list(agent_ids), "max_rounds": rounds}
    )


def test_debate_runs_every_turn_then_writes_report(auth_client, fake_llm):
    r = create(auth_client)
    assert r.status_code == 201
    data = wait_for(auth_client, r.json()["id"])

    assert data["status"] == "completed"
    assert data["current_round"] == 2
    assert [m["round_number"] for m in data["messages"]] == [1, 1, 1, 2, 2, 2]
    assert [m["agent_id"] for m in data["messages"]] == [1, 2, 3, 1, 2, 3]
    assert all(m["status"] == "complete" for m in data["messages"])
    assert data["summary"].startswith("## Verdict")
    assert len(fake_llm.calls) == 7  # six turns + moderator


def test_later_turns_see_earlier_transcript(auth_client, fake_llm):
    wait_for(auth_client, create(auth_client, agent_ids=(1, 2), rounds=2).json()["id"])
    last_turn = fake_llm.calls[3][1]["content"]
    assert "### Round 1" in last_turn and "Reply #1" in last_turn and "Reply #3" in last_turn
    assert "round 2 of 2" in last_turn and "final round" in last_turn


def test_create_validates_input(auth_client):
    assert create(auth_client, topic="short").status_code == 422
    assert create(auth_client, agent_ids=(1,)).status_code == 422
    assert create(auth_client, rounds=9).status_code == 422
    r = create(auth_client, agent_ids=(1, 999))
    assert r.status_code == 422 and "at least 2" in r.json()["detail"]


def test_create_requires_configured_provider(client):
    app.state.runner = DebateRunner()  # no fake LLM and no NVIDIA_API_KEY
    register_and_login(client)
    r = create(client)
    assert r.status_code == 503 and "NVIDIA_API_KEY" in r.json()["detail"]


def test_users_cannot_see_each_others_debates(client):
    register_and_login(client, "alice")
    debate_id = create(client).json()["id"]
    wait_for(client, debate_id)
    register_and_login(client, "mallory")
    assert client.get(f"/api/debates/{debate_id}").status_code == 404
    assert client.get(f"/debates/{debate_id}").status_code == 404
    assert client.delete(f"/api/debates/{debate_id}").status_code == 404
    assert client.get("/api/debates").json() == []


def test_stop_keeps_partial_transcript(auth_client, fake_llm):
    fake_llm.delay = 0.02
    debate_id = create(auth_client, rounds=3).json()["id"]
    wait_for(auth_client, debate_id, statuses=("in_progress",))
    r = auth_client.post(f"/api/debates/{debate_id}/stop")
    assert r.status_code == 200 and r.json()["status"] == "stopped"
    data = auth_client.get(f"/api/debates/{debate_id}").json()
    assert data["summary"] is None
    assert all(m["status"] == "complete" for m in data["messages"])
    assert auth_client.post(f"/api/debates/{debate_id}/stop").status_code == 409


def test_provider_failure_marks_debate_failed(auth_client, fake_llm):
    fake_llm.fail_after_calls = 2
    data = wait_for(auth_client, create(auth_client).json()["id"])
    assert data["status"] == "failed"
    assert "rate limit" in data["error"]
    assert len(data["messages"]) == 2


def test_delete_removes_debate(auth_client):
    debate_id = create(auth_client).json()["id"]
    wait_for(auth_client, debate_id)
    assert auth_client.delete(f"/api/debates/{debate_id}").status_code == 204
    assert auth_client.get(f"/api/debates/{debate_id}").status_code == 404


def test_stop_while_queued_marks_debate_stopped(client, fake_llm):
    fake_llm.delay = 0.02
    app.state.runner = DebateRunner(llm=fake_llm, max_concurrent=1)
    register_and_login(client)
    running = create(client, rounds=3).json()["id"]
    queued = create(client, rounds=3).json()["id"]
    wait_for(client, running, statuses=("in_progress",))
    assert client.get(f"/api/debates/{queued}").json()["status"] == "pending"

    r = client.post(f"/api/debates/{queued}/stop")
    assert r.status_code == 200 and r.json()["status"] == "stopped"
    client.post(f"/api/debates/{running}/stop")
