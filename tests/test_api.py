from pathlib import Path
import pytest
from app.services.analysis import EvaluationService
from app.services.video import InvalidVideo


def result(movement="pukulan"):
    return {
        "movement": movement,
        "matched_variant": None,
        "reference_profile_id": None,
        "score": None,
        "status": "reference_not_ready",
        "pose_status": "detected",
        "analysis": {"frames_processed": 1, "valid_pose_frames": 1, "key_frame": None},
        "issues": [],
        "model": {"analyzer_version": "prototype-v1", "reference_version": None},
    }


def upload(client, member):
    return client.post(
        "/api/v1/evaluations",
        headers=member,
        data={"movement_type": "pukulan"},
        files={"video": ("test.mp4", b"video bytes", "video/mp4")},
    )


def test_authentication_and_refresh_rotation(client, member):
    assert client.get("/api/v1/auth/me", headers=member).json()["role"] == "MEMBER"
    assert client.get("/api/v1/auth/me").status_code == 401
    assert (
        client.post(
            "/api/v1/auth/login",
            json={"email": "one@example.com", "password": "incorrect"},
        ).status_code
        == 401
    )
    old = client.cookies.get("refresh_token")
    assert client.post("/api/v1/auth/refresh").status_code == 200
    new = client.cookies.get("refresh_token")
    assert old != new
    client.cookies.clear()
    client.cookies.set("refresh_token", old)
    assert client.post("/api/v1/auth/refresh").status_code == 401
    client.cookies.clear()
    client.cookies.set("refresh_token", new)
    assert client.post("/api/v1/auth/logout").status_code == 204
    assert client.post("/api/v1/auth/refresh").status_code == 401


def test_role_escalation_forbidden(client, member):
    assert client.get("/api/v1/coach/members", headers=member).status_code == 403
    assert (
        client.patch(
            "/api/v1/profile",
            headers=member,
            json={"name": "Attacker", "role": "COACH"},
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/v1/auth/register",
            json={
                "name": "Attacker",
                "email": "bad@example.com",
                "password": "password123",
                "role": "COACH",
            },
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/v1/auth/refresh", headers={"Origin": "https://evil.example"}
        ).status_code
        == 403
    )


def test_history_isolation_coach_notes_and_cleanup(client, member, monkeypatch):
    paths = []

    def analyze(self, path, movement, profiles):
        assert path.exists()
        paths.append(path)
        return result(movement)

    monkeypatch.setattr(EvaluationService, "analyze", analyze)
    response = upload(client, member)
    assert response.status_code == 201, response.text
    evaluation_id = response.json()["id"]
    assert not paths[0].exists() and not paths[0].parent.exists()
    assert response.json()["score"] is None
    assert len(client.get("/api/v1/evaluations", headers=member).json()) == 1
    other = client.post(
        "/api/v1/auth/register",
        json={"name": "Other", "email": "other@example.com", "password": "password123"},
    ).json()
    headers = {"Authorization": "Bearer " + other["access_token"]}
    assert (
        client.get(f"/api/v1/evaluations/{evaluation_id}", headers=headers).status_code
        == 404
    )
    assert client.get("/api/v1/evaluations", headers=headers).json() == []
    coach = client.post(
        "/api/v1/auth/login",
        json={"email": "coach@example.com", "password": "password123"},
    ).json()
    coach_headers = {"Authorization": "Bearer " + coach["access_token"]}
    owner = client.get("/api/v1/auth/me", headers=member).json()["id"]
    from contextlib import contextmanager
    from app.main import app
    from app.db.session import get_db
    from app.services.assignments import assign_coach
    with contextmanager(app.dependency_overrides[get_db])() as db:
        assign_coach(db, owner, coach["user"]["id"], "test-admin", "Assigned for scoped legacy API test")
    assert len(client.get("/api/v1/coach/members", headers=coach_headers).json()) == 1
    assert (
        len(
            client.get(
                f"/api/v1/coach/members/{owner}/evaluations", headers=coach_headers
            ).json()
        )
        == 1
    )
    assert (
        client.get(
            f"/api/v1/evaluations/{evaluation_id}", headers=coach_headers
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/api/v1/coach/evaluations/{evaluation_id}/notes",
            headers=coach_headers,
            json={"note": "Latih posisi secara perlahan."},
        ).status_code
        == 201
    )
    assert (
        client.get(f"/api/v1/evaluations/{evaluation_id}", headers=member).json()[
            "coach_notes"
        ][0]["coach_name"]
        == "Coach"
    )


@pytest.mark.parametrize(
    "failure,code",
    [
        (InvalidVideo("bad video"), 422),
        (RuntimeError("failed"), 500),
        (FileNotFoundError(), 503),
    ],
)
def test_failed_analysis_cleanup(client, member, monkeypatch, failure, code):
    paths = []

    def analyze(self, path, *args):
        paths.append(path)
        raise failure

    monkeypatch.setattr(EvaluationService, "analyze", analyze)
    assert upload(client, member).status_code == code
    assert not paths[0].parent.exists()
    assert client.get("/api/v1/evaluations", headers=member).json() == []


def test_video_validation(client, member):
    assert (
        client.post(
            "/api/v1/evaluations",
            headers=member,
            data={"movement_type": "pukulan"},
            files={"video": ("bad.exe", b"bad", "application/octet-stream")},
        ).status_code
        == 415
    )
    assert (
        client.post(
            "/api/v1/evaluations",
            headers=member,
            data={"movement_type": "pukulan"},
            files={"video": ("empty.mp4", b"", "video/mp4")},
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/v1/evaluations",
            headers=member,
            data={"movement_type": "unknown"},
            files={"video": ("test.mp4", b"bad", "video/mp4")},
        ).status_code
        == 422
    )


def test_profile_duplicate_email_and_movements(client, member):
    assert (
        client.patch(
            "/api/v1/profile", headers=member, json={"name": "Updated"}
        ).json()["name"]
        == "Updated"
    )
    assert (
        client.post(
            "/api/v1/auth/register",
            json={
                "name": "Other",
                "email": "ONE@example.com",
                "password": "password123",
            },
        ).status_code
        == 409
    )
    assert len(client.get("/api/v1/movements").json()) == 4


def test_upload_limit_cleanup(client, member, monkeypatch):
    import tempfile
    from app.core.config import settings
    from app.services import uploads

    directories = []
    original = tempfile.TemporaryDirectory

    def directory(*args, **kwargs):
        value = original(*args, **kwargs)
        directories.append(Path(value.name))
        return value

    monkeypatch.setattr(uploads, "TemporaryDirectory", directory)
    monkeypatch.setattr(settings, "max_video_mb", 0)
    assert upload(client, member).status_code == 413
    assert directories and all(not d.exists() for d in directories)
