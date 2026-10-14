from datetime import timedelta

import pytest
from sqlmodel import Session, select

from app.config import get_settings
from app.database import engine
from app.models import DebateStart, User
from app.models.debate import utcnow
from tests.conftest import wait_for
from tests.test_debates import create


@pytest.fixture
def limit(monkeypatch):
    def set_limit(n: int):
        monkeypatch.setattr(get_settings(), "daily_debate_limit", n)

    return set_limit


def test_limit_blocks_further_debates_with_retry_after(auth_client, limit):
    limit(2)
    for _ in range(2):
        wait_for(auth_client, create(auth_client).json()["id"])

    r = create(auth_client)
    assert r.status_code == 429
    assert "2 debates in the last 24 hours" in r.json()["detail"]
    assert 0 < int(r.headers["Retry-After"]) <= 24 * 3600


def test_deleting_a_debate_does_not_refund_it(auth_client, limit):
    limit(1)
    debate_id = create(auth_client).json()["id"]
    wait_for(auth_client, debate_id)
    assert auth_client.delete(f"/api/debates/{debate_id}").status_code == 204
    assert create(auth_client).status_code == 429


def test_starts_older_than_24_hours_do_not_count(auth_client, limit):
    limit(1)
    with Session(engine) as db:
        user = db.exec(select(User).where(User.username == "alice")).one()
        db.add(DebateStart(user_id=user.id, created_at=utcnow() - timedelta(hours=25)))
        db.commit()
    assert create(auth_client).status_code == 201


def test_admins_are_exempt(auth_client, limit):
    limit(1)
    with Session(engine) as db:
        user = db.exec(select(User).where(User.username == "alice")).one()
        user.role = "admin"
        db.add(user)
        db.commit()
    for _ in range(2):
        assert create(auth_client).status_code == 201


def test_zero_means_unlimited(auth_client, limit):
    limit(0)
    for _ in range(3):
        wait_for(auth_client, create(auth_client).json()["id"])
    assert create(auth_client).status_code == 201


def test_new_debate_page_shows_remaining_and_blocks_at_zero(auth_client, limit):
    limit(2)
    assert "2 of 2 debates left" in auth_client.get("/debates/new").text
    wait_for(auth_client, create(auth_client).json()["id"])
    assert "1 of 2 debates left" in auth_client.get("/debates/new").text
    wait_for(auth_client, create(auth_client).json()["id"])
    page = auth_client.get("/debates/new").text
    assert "limit of 2 debates per 24 hours" in page
    assert 'type="submit" disabled' in page


def test_htmx_form_shows_limit_inline(auth_client, limit):
    limit(1)
    wait_for(auth_client, create(auth_client).json()["id"])
    r = auth_client.post(
        "/debates",
        data={"topic": "Another long enough topic", "agent_ids": ["1", "2"], "max_rounds": "1"},
        headers={"HX-Request": "true"},
    )
    assert r.status_code == 429
    assert 'class="alert alert-danger"' in r.text
    assert "1 debate in the last 24 hours" in r.text  # singular when the limit is 1
