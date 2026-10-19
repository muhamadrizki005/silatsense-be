from datetime import timedelta
from contextlib import contextmanager

import jwt
import pytest
from sqlalchemy import select

from app.core.config import settings
from app.core.security import token_hash
from app.db.session import get_db
from app.main import app
from app.models.entities import RefreshToken, now


def signup(client, identifier="227006104"):
    return client.post("/api/v1/auth/sign-up", json={
        "fullName": "Member Silat", "identifier": identifier, "password": "password123",
    })


@pytest.mark.parametrize("identifier", ["227006104", "Member@Example.com"])
def test_frontend_signup_signin_session(client, identifier):
    response = signup(client, identifier)
    assert response.status_code == 201, response.text
    payload = response.json()
    assert set(payload) == {"user", "accessToken", "expiresIn"}
    assert payload["user"] == {
        "id": payload["user"]["id"], "fullName": "Member Silat",
        "identifier": identifier.lower(), "role": "member",
    }
    assert isinstance(payload["user"]["id"], str)
    assert payload["expiresIn"] == 900
    assert response.headers["cache-control"] == "no-store"
    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie and "SameSite=strict" in cookie
    assert "Max-Age" not in cookie
    headers = {"Authorization": "Bearer " + payload["accessToken"]}
    assert client.get("/api/v1/auth/session", headers=headers).json() == payload["user"]
    assert client.get("/api/v1/coach/members", headers=headers).status_code == 403
    assert client.get("/api/v1/auth/session").status_code == 401
    assert signup(client, identifier.lower()).status_code == 409
    login = client.post("/api/v1/auth/sign-in", json={
        "identifier": identifier, "password": "password123", "rememberMe": True,
    })
    assert login.status_code == 200
    assert "Max-Age=604800" in login.headers["set-cookie"]


@pytest.mark.parametrize("remember", [False, True])
def test_frontend_rotation_logout_and_expiration(client, remember):
    signup(client)
    login = client.post("/api/v1/auth/sign-in", json={
        "identifier": "227006104", "password": "password123", "rememberMe": remember,
    })
    assert login.status_code == 200
    old = client.cookies.get("refresh_token")
    factory = contextmanager(app.dependency_overrides[get_db])
    with factory() as db:
        row = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == token_hash(old)))
        deadline = row.expires_at
        assert timedelta(days=7 if remember else 1) - timedelta(seconds=10) < deadline - now()
    rotated = client.post("/api/v1/auth/refresh-session")
    assert rotated.status_code == 200
    assert "accessToken" in rotated.json()
    assert ("Max-Age=" in rotated.headers["set-cookie"]) == remember
    new = client.cookies.get("refresh_token")
    with factory() as db:
        row = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == token_hash(new)))
        assert row.expires_at == deadline
    client.cookies.clear()
    client.cookies.set("refresh_token", old, domain="testserver.local", path="/api/v1/auth")
    assert client.post("/api/v1/auth/refresh-session").status_code == 401
    client.cookies.clear()
    client.cookies.set("refresh_token", new, domain="testserver.local", path="/api/v1/auth")
    assert client.post("/api/v1/auth/logout").status_code == 204
    assert client.cookies.get("refresh_token") is None
    client.cookies.set("refresh_token", new, domain="testserver.local", path="/api/v1/auth")
    assert client.post("/api/v1/auth/refresh-session").status_code == 401
    client.cookies.clear()
    signup(client, "expired@example.com")
    with factory() as db:
        row = db.scalar(select(RefreshToken).where(
            RefreshToken.token_hash == token_hash(client.cookies.get("refresh_token")),
        ))
        row.expires_at = now() - timedelta(seconds=1)
        db.commit()
    assert client.post("/api/v1/auth/refresh-session").status_code == 401


@pytest.mark.parametrize("changes", [
    {"identifier": "123"}, {"identifier": "bad-email"},
    {"identifier": "１２３４５６７８"}, {"fullName": "   "},
    {"password": "short"}, {"role": "coach"},
])
def test_signup_validation_and_role_injection(client, changes):
    data = {"fullName": "Member Silat", "identifier": "227006104", "password": "password123"}
    data.update(changes)
    assert client.post("/api/v1/auth/sign-up", json=data).status_code == 422


def test_failed_signin_and_origin(client):
    signup(client)
    for identifier in ["227006104", "999999999"]:
        response = client.post("/api/v1/auth/sign-in", json={
            "identifier": identifier, "password": "incorrect",
        })
        assert response.status_code == 401
        assert "set-cookie" not in response.headers
    for path in ["sign-up", "sign-in", "refresh-session", "logout"]:
        response = client.post("/api/v1/auth/" + path,
                               headers={"Origin": "https://evil.example"}, json={})
        assert response.status_code == 403
    coach = client.post("/api/v1/auth/sign-in", json={
        "identifier": "coach@example.com", "password": "password123",
    })
    assert coach.json()["user"]["role"] == "coach"


@pytest.mark.parametrize("claims", [
    {"sub": "1", "type": "access"},
    {"sub": "1", "type": "refresh", "exp": 4102444800},
    {"sub": None, "type": "access", "exp": 4102444800},
    {"sub": "1", "type": "access", "exp": 1},
])
def test_invalid_access_tokens(client, claims):
    token = jwt.encode(claims, settings.jwt_secret, algorithm="HS256")
    assert client.get("/api/v1/auth/session", headers={
        "Authorization": "Bearer " + token,
    }).status_code == 401
