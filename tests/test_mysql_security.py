"""Lock/race behavior; run only against the disposable TEST_DATABASE_URL fixture."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import os
from threading import Event

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api import auth as routes
from app.db.session import get_db
from app.main import app
from app.models.entities import RefreshToken, User
from app.services import profiles

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL", "").startswith("mysql"),
    reason="Requires isolated disposable MySQL for row-lock concurrency",
)


def registered(client):
    response = client.post("/api/v1/auth/sign-up", json={
        "fullName": "Race Member", "identifier": "227006104", "password": "password123",
    })
    assert response.status_code == 201
    return response.json(), client.cookies.get("refresh_token")


def refresh_request(token):
    with TestClient(app, raise_server_exceptions=False) as client:
        client.cookies.set("refresh_token", token, domain="testserver.local", path="/api/v1/auth")
        return client.post("/api/v1/auth/refresh-session")


def password_request(access):
    with TestClient(app, raise_server_exceptions=False) as client:
        return client.patch("/api/v1/member/password", headers={"Authorization": "Bearer " + access},
                            json={"currentPassword": "password123", "newPassword": "changed-password123"})


def test_refresh_race_has_single_winner(client):
    body, token = registered(client)
    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs = [pool.submit(refresh_request, token) for _ in range(2)]
        responses = [job.result(timeout=15) for job in jobs]
    assert sorted(response.status_code for response in responses) == [200, 401]
    assert refresh_request(token).status_code == 401


@pytest.mark.parametrize("first", ["refresh", "password"])
def test_refresh_and_password_change_are_serialized(client, monkeypatch, first):
    body, token = registered(client)
    locked, release = Event(), Event()
    module = routes if first == "refresh" else profiles
    original = module.lock_user

    def hold_user_lock(db, user_id):
        user = original(db, user_id)
        locked.set()
        assert release.wait(timeout=10)
        return user

    monkeypatch.setattr(module, "lock_user", hold_user_lock)
    with ThreadPoolExecutor(max_workers=2) as pool:
        if first == "refresh":
            refresh_job = pool.submit(refresh_request, token)
            assert locked.wait(timeout=10)
            password_job = pool.submit(password_request, body["accessToken"])
        else:
            password_job = pool.submit(password_request, body["accessToken"])
            assert locked.wait(timeout=10)
            refresh_job = pool.submit(refresh_request, token)
        release.set()
        refreshed = refresh_job.result(timeout=15)
        changed = password_job.result(timeout=15)
    assert changed.status_code == 204, changed.text
    assert refreshed.status_code == (200 if first == "refresh" else 401), refreshed.text
    if refreshed.status_code == 200:
        assert refresh_request(refreshed.cookies.get("refresh_token")).status_code == 401
        access = refreshed.json()["accessToken"]
        assert client.get("/api/v1/auth/session", headers={"Authorization": "Bearer " + access}).status_code == 401
    with contextmanager(app.dependency_overrides[get_db])() as db:
        user = db.get(User, int(body["user"]["id"]))
        assert user.auth_version == 1
        assert all(row.revoked for row in db.scalars(select(RefreshToken).where(RefreshToken.user_id == user.id)))


def test_login_cannot_issue_tokens_for_old_password_after_change(client, monkeypatch):
    body, token = registered(client)
    locked, release = Event(), Event()
    original = profiles.lock_user

    def hold_user_lock(db, user_id):
        user = original(db, user_id)
        locked.set()
        assert release.wait(timeout=10)
        return user

    monkeypatch.setattr(profiles, "lock_user", hold_user_lock)
    def old_login():
        with TestClient(app, raise_server_exceptions=False) as other:
            return other.post("/api/v1/auth/sign-in", json={"identifier": "227006104", "password": "password123"})
    with ThreadPoolExecutor(max_workers=2) as pool:
        changed = pool.submit(password_request, body["accessToken"])
        assert locked.wait(timeout=10)
        login = pool.submit(old_login)
        release.set()
        assert changed.result(timeout=15).status_code == 204
        assert login.result(timeout=15).status_code == 401
