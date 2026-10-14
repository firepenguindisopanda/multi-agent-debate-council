from fastapi.testclient import TestClient

from app.main import app


def test_register_rejects_invalid_input(client):
    r = client.post(
        "/register", data={"username": "a!", "email": "x@example.com", "password": "password123"}
    )
    assert r.status_code == 422
    assert "Username must be" in r.text

    r = client.post(
        "/register", data={"username": "bob", "email": "x@example.com", "password": "short"}
    )
    assert r.status_code == 422
    assert "at least 8 characters" in r.text


def test_register_reports_duplicates_specifically(client):
    data = {"username": "bob", "email": "bob@example.com", "password": "password123"}
    assert client.post("/register", data=data, follow_redirects=False).status_code == 303
    r = client.post("/register", data={**data, "email": "other@example.com"})
    assert "username is taken" in r.text
    r = client.post("/register", data={**data, "username": "bobby"})
    assert "email already exists" in r.text


def test_login_sets_lax_httponly_cookie(client):
    client.post(
        "/register", data={"username": "bob", "email": "bob@example.com", "password": "password123"}
    )
    r = client.post(
        "/login", data={"username": "bob", "password": "password123"}, follow_redirects=False
    )
    cookie = r.headers["set-cookie"].lower()
    assert r.headers["location"] == "/debates"
    assert "httponly" in cookie and "samesite=lax" in cookie


def test_login_failure_shows_error(client):
    r = client.post("/login", data={"username": "nobody", "password": "password123"})
    assert r.status_code == 401
    assert "Incorrect username or password" in r.text


def test_login_rejects_open_redirect(client):
    client.post(
        "/register", data={"username": "bob", "email": "bob@example.com", "password": "password123"}
    )
    r = client.post(
        "/login",
        data={"username": "bob", "password": "password123", "next": "//evil.example.com"},
        follow_redirects=False,
    )
    assert r.headers["location"] == "/debates"


def test_pages_redirect_to_login_and_api_returns_json_401(client):
    r = client.get("/debates", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/login?next=/debates"
    r = client.get("/api/debates")
    assert r.status_code == 401 and r.json()["detail"] == "Could not validate credentials"


def test_users_api_is_admin_only(auth_client):
    assert auth_client.get("/api/users").status_code == 403
    assert auth_client.get("/admin").status_code == 403


def test_bearer_token_auth(client):
    client.post(
        "/register", data={"username": "bob", "email": "bob@example.com", "password": "password123"}
    )
    token = client.post(
        "/api/auth/token", data={"username": "bob", "password": "password123"}
    ).json()["access_token"]
    fresh = TestClient(app)
    r = fresh.get("/api/agents", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200 and len(r.json()) == 6
