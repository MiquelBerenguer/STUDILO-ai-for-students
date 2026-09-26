from __future__ import annotations

from fastapi.testclient import TestClient

from app.auth.security import COOKIE_NAME
from tests.conftest import make_client, register


def test_register_login_logout_cycle(app) -> None:  # type: ignore[no-untyped-def]
    c = make_client(app)
    me = register(c, "Bob@Example.com", "s3cret-password")
    assert me["email"] == "bob@example.com" and me["journey_state"] == "onboarding"
    assert c.get("/api/v1/auth/me").status_code == 200
    assert c.post("/api/v1/auth/logout").status_code == 204
    assert c.get("/api/v1/auth/me").status_code == 401
    assert c.post("/api/v1/auth/login", json={"email": "bob@example.com", "password": "wrong-password"}).status_code == 401
    r = c.post("/api/v1/auth/login", json={"email": "bob@example.com", "password": "s3cret-password"})
    assert r.status_code == 200
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie


def test_logout_revokes_the_session_server_side(app) -> None:  # type: ignore[no-untyped-def]
    c = make_client(app)
    register(c, "carol@example.com")
    token = c.cookies.get(COOKIE_NAME)
    c.post("/api/v1/auth/logout")
    stolen = make_client(app)
    stolen.cookies.set(COOKIE_NAME, token)
    assert stolen.get("/api/v1/auth/me").status_code == 401


def test_password_is_hashed_and_duplicates_rejected(app) -> None:  # type: ignore[no-untyped-def]
    from sqlalchemy import select

    from app.db.engine import system_session_ctx
    from app.db.models import AuthSession, User

    c = make_client(app)
    register(c, "dave@example.com", "plain-text-pw")
    with system_session_ctx() as db:
        user = db.scalar(select(User).where(User.email == "dave@example.com"))
        assert user.password_hash.startswith("$2") and "plain-text-pw" not in user.password_hash
        token = c.cookies.get(COOKIE_NAME)
        assert db.scalar(select(AuthSession).where(AuthSession.token_hash == token)) is None  # only the HMAC is stored
    assert c.post("/api/v1/auth/register", json={"email": "dave@example.com", "password": "another-pw1"}).status_code == 409
    assert c.post("/api/v1/auth/register", json={"email": "x@example.com", "password": "short"}).status_code == 422


def test_every_non_public_endpoint_requires_auth(app) -> None:  # type: ignore[no-untyped-def]
    public = {("POST", "/api/v1/auth/register"), ("POST", "/api/v1/auth/login"), ("POST", "/api/v1/auth/logout"),
              ("GET", "/api/v1/health"), ("GET", "/api/v1/meta")}
    anon = TestClient(app)
    checked = 0
    for path, ops in app.openapi()["paths"].items():
        for method in (m.upper() for m in ops):
            if (method, path) in public:
                continue
            url = path.replace("{", "").replace("}", "")  # any placeholder value works: auth is checked first
            r = anon.request(method, url)
            assert r.status_code == 401, f"{method} {path} -> {r.status_code}"
            checked += 1
    assert checked > 40
