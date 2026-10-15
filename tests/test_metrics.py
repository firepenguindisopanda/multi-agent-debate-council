"""Per-call metrics, debate provenance and the report contract."""

from sqlmodel import Session, select

from app.database import engine
from app.models import Agent, Debate, LLMCall, LLMCallKind
from app.services import prompts
from tests.conftest import wait_for
from tests.fakes import REPORT
from tests.test_debates import create


def calls_for(debate_id: int) -> list[LLMCall]:
    with Session(engine) as db:
        return list(
            db.exec(select(LLMCall).where(LLMCall.debate_id == debate_id).order_by(LLMCall.id))
        )


def test_records_one_call_per_turn_plus_the_summary(auth_client):
    data = wait_for(auth_client, create(auth_client, agent_ids=(1, 2), rounds=2).json()["id"])
    calls = calls_for(data["id"])

    assert [c.kind for c in calls] == [LLMCallKind.TURN] * 4 + [LLMCallKind.SUMMARY]
    assert [c.message_id for c in calls[:4]] == [m["id"] for m in data["messages"]]
    assert calls[-1].message_id is None
    for call in calls:
        assert call.input_tokens > 0 and call.output_tokens > 0
        assert call.finish_reason == "stop" and call.error is None and call.retries == 0
        assert call.response_model == "fake/scripted-model"
    # Every turn resends the transcript, so input grows turn by turn.
    turn_inputs = [c.input_tokens for c in calls[:4]]
    assert turn_inputs == sorted(turn_inputs) and turn_inputs[0] < turn_inputs[-1]


def test_debate_records_provenance(auth_client):
    debate_id = create(auth_client, agent_ids=(1, 2), rounds=1).json()["id"]
    wait_for(auth_client, debate_id)
    with Session(engine) as db:
        debate = db.get(Debate, debate_id)
        agents = [p.agent for p in debate.participants]
        assert debate.llm_model == "fake/scripted-model"
        assert debate.llm_temperature is not None and debate.llm_top_p is not None
        assert debate.llm_max_tokens and debate.llm_summary_max_tokens
        assert debate.prompt_version == prompts.prompt_version(agents)


def test_prompt_version_tracks_prompt_text_not_speaking_order(monkeypatch):
    a = Agent(name="A", role="A", system_prompt="You are A.")
    b = Agent(name="B", role="B", system_prompt="You are B.")
    base = prompts.prompt_version([a, b])
    assert len(base) == 12
    assert prompts.prompt_version([b, a]) == base
    assert prompts.prompt_version([a, Agent(name="B", role="B", system_prompt="Changed.")]) != base
    monkeypatch.setattr(prompts, "TURN_RULES", prompts.TURN_RULES + " Be brief.")
    assert prompts.prompt_version([a, b]) != base


def test_failed_call_is_recorded_with_its_error(auth_client, fake_llm):
    fake_llm.fail_after_calls = 2
    debate_id = create(auth_client, agent_ids=(1, 2), rounds=2).json()["id"]
    assert wait_for(auth_client, debate_id)["status"] == "failed"
    calls = calls_for(debate_id)
    assert [c.error for c in calls] == [None, None, "LLMError"]
    assert calls[-1].message_id is None


def test_stopped_call_is_recorded_as_cancelled(auth_client, fake_llm):
    fake_llm.delay = 0.02
    debate_id = create(auth_client, rounds=3).json()["id"]
    wait_for(auth_client, debate_id, statuses=("in_progress",))
    auth_client.post(f"/api/debates/{debate_id}/stop")
    assert calls_for(debate_id)[-1].error == "CancelledError"


def test_deleting_a_debate_removes_its_calls(auth_client):
    debate_id = create(auth_client, agent_ids=(1, 2), rounds=1).json()["id"]
    wait_for(auth_client, debate_id)
    assert calls_for(debate_id)
    assert auth_client.delete(f"/api/debates/{debate_id}").status_code == 204
    assert calls_for(debate_id) == []


def test_report_contract():
    assert all(f"## {s}" in prompts.MODERATOR_PROMPT for s in prompts.REPORT_SECTIONS)
    assert prompts.missing_report_sections(REPORT) == []
    assert prompts.missing_report_sections("## Verdict\nShip.\n## Key risks\n") == [
        "Agreed requirements",
        "Open questions",
        "Key risks",  # present but empty
        "Recommended next steps",
    ]
    # Heading depth and case don't matter.
    lenient = REPORT.replace("## Verdict", "### verdict")
    assert prompts.missing_report_sections(lenient) == []


def test_completed_debate_report_meets_the_contract(auth_client):
    data = wait_for(auth_client, create(auth_client, rounds=1).json()["id"])
    assert prompts.missing_report_sections(data["summary"]) == []


def test_run_details_in_api_export_and_page(auth_client, fake_llm):
    debate_id = create(auth_client, agent_ids=(1, 2), rounds=1).json()["id"]
    data = wait_for(auth_client, debate_id)

    run = data["run"]
    assert data["llm_model"] == "fake/scripted-model" and len(data["prompt_version"]) == 12
    assert run["calls"] == 3 and run["failed_calls"] == 0 and run["truncated_calls"] == 0
    assert run["input_tokens"] > run["output_tokens"] > 0

    export = auth_client.get(f"/debates/{debate_id}/export.md").text
    assert "## Run details" in export and "Prompt version: " + data["prompt_version"] in export

    page = auth_client.get(f"/debates/{debate_id}").text
    assert "Run details" in page and data["prompt_version"] in page


def test_run_details_hidden_while_running(auth_client, fake_llm):
    fake_llm.delay = 0.02
    debate_id = create(auth_client, rounds=3).json()["id"]
    wait_for(auth_client, debate_id, statuses=("in_progress",))
    assert "Run details" not in auth_client.get(f"/debates/{debate_id}").text
    assert auth_client.get(f"/api/debates/{debate_id}").json()["status"] == "in_progress"
    auth_client.post(f"/api/debates/{debate_id}/stop")
