from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from threading import Barrier
import os

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.db.session import get_db
from app.core.errors import DomainError
from app.models.entities import User, RefreshToken
from app.services.mail import MemoryMailAdapter, get_mail_adapter
from app.services.recovery import rate_limit

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL", "").startswith("mysql"),
    reason="Recovery races require disposable native MySQL row locks",
)


@pytest.fixture
def recovery(client):
    mail = MemoryMailAdapter()
    app.dependency_overrides[get_mail_adapter] = lambda: mail
    body = client.post(
        "/api/v1/auth/sign-up",
        json=dict(
            fullName="Native Recovery",
            identifier="race@example.com",
            password="password123",
        ),
    ).json()
    auth = {"Authorization": "Bearer " + body["accessToken"]}
    assert (
        client.post(
            "/api/v1/auth/email-verification/request",
            headers=auth,
            json={"currentPassword": "password123"},
        ).status_code
        == 202
    )
    assert (
        client.post(
            "/api/v1/auth/email-verification/confirm",
            headers=auth,
            json={"token": mail.messages[-1]["token"]},
        ).status_code
        == 204
    )
    assert (
        client.post(
            "/api/v1/auth/password-reset/request",
            json={"identifier": "race@example.com"},
        ).status_code
        == 202
    )
    with contextmanager(app.dependency_overrides[get_db])() as db:
        factory = sessionmaker(bind=db.bind, expire_on_commit=False)
    yield dict(
        mail=mail,
        auth=auth,
        body=body,
        factory=factory,
        token=mail.messages[-1]["token"],
        refresh=client.cookies.get("refresh_token"),
    )
    app.dependency_overrides.pop(get_mail_adapter, None)


def test_parallel_reset_has_exactly_one_winner(client, recovery):
    barrier = Barrier(2)

    def work(_):
        with TestClient(app) as other:
            barrier.wait(timeout=10)
            return other.post(
                "/api/v1/auth/password-reset/confirm",
                json={"token": recovery["token"], "newPassword": "changed-password123"},
            )

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(work, range(2)))
    assert sorted(r.status_code for r in responses) == [204, 422]
    with recovery["factory"]() as db:
        assert db.get(User, int(recovery["body"]["user"]["id"])).auth_version == 1
        assert all(token.revoked for token in db.scalars(select(RefreshToken)))


def test_refresh_racing_reset_never_leaves_a_valid_old_session(client, recovery):
    barrier = Barrier(2)

    def refresh():
        with TestClient(app) as other:
            other.cookies.set(
                "refresh_token",
                recovery["refresh"],
                domain="testserver.local",
                path="/api/v1/auth",
            )
            barrier.wait(timeout=10)
            return other.post("/api/v1/auth/refresh-session")

    def reset():
        with TestClient(app) as other:
            barrier.wait(timeout=10)
            return other.post(
                "/api/v1/auth/password-reset/confirm",
                json={"token": recovery["token"], "newPassword": "changed-password123"},
            )

    with ThreadPoolExecutor(max_workers=2) as pool:
        rotated = pool.submit(refresh)
        changed = pool.submit(reset)
        result = rotated.result(timeout=15)
        assert changed.result(timeout=15).status_code == 204
    assert result.status_code in (200, 401)
    if result.status_code == 200:
        assert (
            client.get(
                "/api/v1/auth/session",
                headers={"Authorization": "Bearer " + result.json()["accessToken"]},
            ).status_code
            == 401
        )
    with recovery["factory"]() as db:
        assert all(token.revoked for token in db.scalars(select(RefreshToken)))


def test_parallel_rate_limit_is_shared_and_atomic(client, recovery):
    barrier = Barrier(8)

    def work(_):
        with recovery["factory"]() as db:
            barrier.wait(timeout=10)
            try:
                rate_limit(db, "test-race", "same-identity", 5, 3600)
                return 200
            except DomainError as error:
                return error.status_code

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(work, range(8)))
    assert results.count(200) == 5 and results.count(429) == 3
