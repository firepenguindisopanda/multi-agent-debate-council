import os
import tempfile

_db_dir = tempfile.mkdtemp()
os.environ.update(
    # CI also runs the suite against Postgres by setting TEST_DATABASE_URI.
    DATABASE_URI=os.environ.get("TEST_DATABASE_URI", f"sqlite:///{_db_dir}/test.db"),
    SECRET_KEY="test-secret-key-that-is-long-enough-for-hs256",
    ENV="test",
    AUTO_MIGRATE="false",
    NVIDIA_API_KEY="",
)

import time  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlmodel import Session  # noqa: E402

from app.data import seed_agents  # noqa: E402
from app.database import create_db_and_tables, drop_all, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.services.debate_runner import DebateRunner  # noqa: E402
from tests.fakes import FakeLLM  # noqa: E402


@pytest.fixture(autouse=True)
def database():
    create_db_and_tables()
    with Session(engine) as db:
        seed_agents(db)
    yield
    drop_all()


@pytest.fixture
def fake_llm():
    return FakeLLM()


@pytest.fixture
def client(fake_llm):
    app.state.runner = DebateRunner(llm=fake_llm)
    with TestClient(app) as c:
        yield c


def register_and_login(client: TestClient, username: str = "alice") -> TestClient:
    client.post(
        "/register",
        data={"username": username, "email": f"{username}@example.com", "password": "password123"},
    )
    r = client.post(
        "/login", data={"username": username, "password": "password123"}, follow_redirects=False
    )
    assert r.status_code == 303
    client.cookies.set("access_token", r.cookies["access_token"])
    return client


@pytest.fixture
def auth_client(client):
    return register_and_login(client)


def wait_for(
    client: TestClient, debate_id: int, statuses=("completed", "stopped", "failed"), timeout=10
):
    deadline = time.time() + timeout
    while time.time() < deadline:
        data = client.get(f"/api/debates/{debate_id}").json()
        if data["status"] in statuses:
            return data
        time.sleep(0.02)
    raise AssertionError(f"debate {debate_id} did not reach {statuses}: {data['status']}")
