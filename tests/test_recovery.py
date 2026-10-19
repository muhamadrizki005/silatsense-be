from datetime import timedelta
from sqlalchemy import select
import pytest

from app.main import app
from app.db.session import get_db
from app.models.entities import RecoveryToken, RefreshToken, User, now
from app.services.mail import MemoryMailAdapter, get_mail_adapter

PREFIX = "/api/v1/auth/"


@pytest.fixture
def mail(client):
    adapter = MemoryMailAdapter()
    app.dependency_overrides[get_mail_adapter] = lambda: adapter
    yield adapter
    app.dependency_overrides.pop(get_mail_adapter, None)


def signup(client, identifier="227006104"):
    response = client.post(
        PREFIX + "sign-up",
        json=dict(
            fullName="Recovery Member", identifier=identifier, password="password123"
        ),
    )
    assert response.status_code == 201
    return {"Authorization": "Bearer " + response.json()["accessToken"]}


def db_session():
    return next(app.dependency_overrides[get_db]())


def request_verify(client, headers):
    return client.post(
        PREFIX + "email-verification/request",
        headers=headers,
        json={"currentPassword": "password123"},
    )


def test_link_is_pending_until_confirm_then_revokes_sessions(client, mail):
    auth = signup(client)
    response = client.post(
        PREFIX + "email-link/request",
        headers=auth,
        json={"email": "LINK@Example.com", "currentPassword": "password123"},
    )
    assert response.status_code == 202 and "requestId" not in response.json()
    assert response.headers["cache-control"] == "no-store"
    assert client.get("/api/v1/member/profile", headers=auth).json()["email"] is None
    with db_session() as db:
        row = db.scalar(select(RecoveryToken))
        assert (
            row.email == "link@example.com"
            and row.token_hash != mail.messages[0]["token"]
        )
        assert 86390 <= (row.expires_at - now()).total_seconds() <= 86400
    assert (
        client.post(
            PREFIX + "email-link/confirm",
            headers=auth,
            json={"token": mail.messages[0]["token"]},
        ).status_code
        == 204
    )
    assert client.get(PREFIX + "session", headers=auth).status_code == 401
    assert client.post(PREFIX + "refresh-session").status_code == 401
    for identifier in ("227006104", "link@example.com"):
        assert (
            client.post(
                PREFIX + "sign-in",
                json={"identifier": identifier, "password": "password123"},
            ).status_code
            == 200
        )


def test_verification_existing_email_and_reset_single_use(client, mail):
    auth = signup(client, "member@example.com")
    assert (
        client.post(
            PREFIX + "password-reset/request", json={"identifier": "member@example.com"}
        ).status_code
        == 202
    )
    assert mail.messages == []
    assert request_verify(client, auth).status_code == 202
    token = mail.messages[-1]["token"]
    assert (
        client.post(
            PREFIX + "email-verification/confirm", headers=auth, json={"token": token}
        ).status_code
        == 204
    )
    assert client.get(PREFIX + "session", headers=auth).status_code == 200
    replay = client.post(
        PREFIX + "email-verification/confirm", headers=auth, json={"token": token}
    )
    assert (
        replay.status_code == 422
        and replay.json()["code"] == "invalid_or_expired_token"
    )
    assert (
        client.post(
            PREFIX + "password-reset/request", json={"identifier": "member@example.com"}
        ).status_code
        == 202
    )
    reset = {"token": mail.messages[-1]["token"], "newPassword": "new-password123"}
    with db_session() as db:
        row = db.scalar(select(RecoveryToken).where(RecoveryToken.purpose == "reset"))
        assert 1790 <= (row.expires_at - now()).total_seconds() <= 1800
    assert client.post(PREFIX + "password-reset/confirm", json=reset).status_code == 204
    assert client.post(PREFIX + "password-reset/confirm", json=reset).status_code == 422
    assert client.get(PREFIX + "session", headers=auth).status_code == 401
    assert client.post(PREFIX + "refresh-session").status_code == 401
    assert (
        client.post(
            PREFIX + "sign-in",
            json={"identifier": "member@example.com", "password": "password123"},
        ).status_code
        == 401
    )
    assert (
        client.post(
            PREFIX + "sign-in",
            json={"identifier": "member@example.com", "password": "new-password123"},
        ).status_code
        == 200
    )


def test_generic_reset_no_email_unknown_and_delivery_failure(client, mail):
    signup(client)
    responses = [
        client.post(PREFIX + "password-reset/request", json={"identifier": identifier})
        for identifier in ("227006104", "unknown@example.com")
    ]
    assert (
        responses[0].json()
        == responses[1].json()
        == {"detail": "Jika memenuhi syarat, instruksi akan dikirim."}
    )
    assert mail.messages == []


def test_reauthentication_rate_limit_persists_failed_attempts(client, mail):
    auth = signup(client)
    for _ in range(5):
        response = client.post(
            PREFIX + "email-link/request",
            headers=auth,
            json={"email": "link@example.com", "currentPassword": "wrong-password"},
        )
        assert (
            response.status_code == 401
            and response.json()["code"] == "invalid_current_password"
        )
    assert (
        client.post(
            PREFIX + "email-link/request",
            headers=auth,
            json={"email": "link@example.com", "currentPassword": "password123"},
        ).status_code
        == 429
    )
    assert mail.messages == []


@pytest.mark.parametrize(
    "kind",
    ["expired", "wrong-purpose", "different-user", "password-changed", "superseded"],
)
def test_invalid_link_tokens(client, mail, kind):
    auth = signup(client)

    def request():
        return client.post(
            PREFIX + "email-link/request",
            headers=auth,
            json={"email": "link@example.com", "currentPassword": "password123"},
        )

    assert request().status_code == 202
    token = mail.messages[-1]["token"]
    if kind == "expired":
        with db_session() as db:
            db.scalar(select(RecoveryToken)).expires_at = now() - timedelta(seconds=1)
            db.commit()
    elif kind == "different-user":
        auth = signup(client, "227006105")
    elif kind == "password-changed":
        assert (
            client.patch(
                "/api/v1/member/password",
                headers=auth,
                json={
                    "currentPassword": "password123",
                    "newPassword": "changed-password",
                },
            ).status_code
            == 204
        )
        login = client.post(
            PREFIX + "sign-in",
            json={"identifier": "227006104", "password": "changed-password"},
        )
        auth = {"Authorization": "Bearer " + login.json()["accessToken"]}
    elif kind == "superseded":
        assert request().status_code == 202
    endpoint = (
        "email-verification/confirm"
        if kind == "wrong-purpose"
        else "email-link/confirm"
    )
    response = client.post(PREFIX + endpoint, headers=auth, json={"token": token})
    assert (
        response.status_code == 422
        and response.json()["code"] == "invalid_or_expired_token"
    )


def test_email_uniqueness_checked_at_confirmation(client, mail):
    auth = signup(client)
    assert (
        client.post(
            PREFIX + "email-link/request",
            headers=auth,
            json={"email": "claimed@example.com", "currentPassword": "password123"},
        ).status_code
        == 202
    )
    token = mail.messages[-1]["token"]
    signup(client, "claimed@example.com")
    result = client.post(
        PREFIX + "email-link/confirm", headers=auth, json={"token": token}
    )
    assert result.status_code == 422
    assert client.get("/api/v1/member/profile", headers=auth).json()["email"] is None


def test_mail_failure_rolls_back_token_and_keeps_old_token(client, mail):
    auth = signup(client, "member@example.com")
    assert request_verify(client, auth).status_code == 202
    original = mail.messages[-1]["token"]

    def fail(*args):
        raise RuntimeError("sensitive delivery error")

    mail.send = fail
    response = request_verify(client, auth)
    assert response.status_code == 503 and "sensitive" not in response.text
    assert (
        client.post(
            PREFIX + "email-verification/confirm",
            headers=auth,
            json={"token": original},
        ).status_code
        == 204
    )
    response = client.post(
        PREFIX + "password-reset/request", json={"identifier": "member@example.com"}
    )
    assert response.status_code == 202
    with db_session() as db:
        assert (
            db.scalar(select(RecoveryToken).where(RecoveryToken.purpose == "reset"))
            is None
        )


def test_origin_and_validation_do_not_echo_tokens_or_passwords(client, mail):
    response = client.post(
        PREFIX + "password-reset/confirm",
        json={"token": "secret", "newPassword": "short"},
    )
    assert response.status_code == 422 and response.json()["code"] == "validation_error"
    assert "secret" not in response.text and "short" not in response.text
    assert (
        client.post(
            PREFIX + "password-reset/request",
            headers={"Origin": "https://evil.example"},
            json={"identifier": "one@example.com"},
        ).status_code
        == 403
    )
    assert client.get(PREFIX + "session").json() == {"detail": "Silakan masuk kembali."}


def test_login_rate_limit_preserves_legacy_error_shape(client, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "auth_attempts_per_15_minutes", 2)
    for _ in range(2):
        assert (
            client.post(
                PREFIX + "sign-in",
                json={
                    "identifier": "missing@example.com",
                    "password": "wrong-password",
                },
            ).status_code
            == 401
        )
    response = client.post(
        PREFIX + "sign-in",
        json={"identifier": "missing@example.com", "password": "wrong-password"},
    )
    assert response.status_code == 429 and set(response.json()) == {"detail"}


@pytest.mark.parametrize("microseconds_before_expiry,expected", [(1, 204), (0, 422)])
def test_token_microseconds_and_exact_deadline(
    client, mail, monkeypatch, microseconds_before_expiry, expected
):
    from app.services import recovery

    frozen = now().replace(microsecond=900123)
    monkeypatch.setattr(recovery, "now", lambda: frozen)
    auth = signup(client)
    response = client.post(
        PREFIX + "email-link/request",
        headers=auth,
        json={"email": "precision@example.com", "currentPassword": "password123"},
    )
    assert response.status_code == 202
    deadline = frozen + timedelta(hours=24)
    with db_session() as db:
        assert db.scalar(select(RecoveryToken)).expires_at == deadline
    monkeypatch.setattr(
        recovery,
        "now",
        lambda: deadline - timedelta(microseconds=microseconds_before_expiry),
    )
    response = client.post(
        PREFIX + "email-link/confirm",
        headers=auth,
        json={"token": mail.messages[-1]["token"]},
    )
    assert response.status_code == expected
