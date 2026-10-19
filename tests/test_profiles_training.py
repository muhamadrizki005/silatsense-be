from contextlib import contextmanager
from datetime import timedelta
import json

import jwt
import pytest
from sqlalchemy import select

from app.core.config import settings
from app.core.security import passwords
from app.db.session import get_db
from app.intelligence.contracts import FEATURE_VERSION
from app.main import app
from app.models.entities import CoachProfile, EvaluationSession, MemberProfile, Movement, ReferenceProfile, RefreshToken, User, now
from app.repositories.training import seed_movements


def database():
    return contextmanager(app.dependency_overrides[get_db])()


def signup(client, identifier="227006104"):
    response = client.post("/api/v1/auth/sign-up", json={
        "fullName": "Member Silat", "identifier": identifier, "password": "password123",
    })
    assert response.status_code == 201, response.text
    body = response.json()
    return body, {"Authorization": "Bearer " + body["accessToken"]}


def assert_domain_error(response, status, code):
    assert response.status_code == status, response.text
    assert response.json()["code"] == code
    assert response.json()["requestId"] == response.headers["x-request-id"]
    assert response.headers["cache-control"] == "no-store"


def test_npm_profile_patch_nulls_and_legacy_contract(client):
    body, headers = signup(client)
    response = client.get("/api/v1/member/profile", headers=headers)
    assert response.status_code == 200
    profile = response.json()
    assert profile["id"] == body["user"]["id"]
    assert profile["npm"] == "227006104" and profile["email"] is None
    assert profile["role"] == "member" and profile["createdAt"].endswith("Z")
    for field in ["division", "title", "belt", "beltTarget", "passwordChangedAt", "emailVerifiedAt", "coach"]:
        assert profile[field] is None
    assert profile["statistics"]["completedSessionCount"] == 0
    assert profile["statistics"]["similarityGroups"] == []
    assert response.headers["cache-control"] == "no-store"
    changed = client.patch("/api/v1/member/profile", headers=headers,
                           json={"fullName": "  Nama Baru  ", "division": "  UKM Silat  "})
    assert changed.json()["fullName"] == "Nama Baru"
    assert changed.json()["division"] == "UKM Silat"
    cleared = client.patch("/api/v1/member/profile", headers=headers, json={"division": None})
    assert cleared.json()["division"] is None
    assert cleared.json()["fullName"] == "Nama Baru"
    legacy = client.get("/api/v1/profile", headers=headers).json()
    assert legacy["name"] == "Nama Baru" and legacy["role"] == "MEMBER"
    assert isinstance(legacy["id"], int) and "fullName" not in legacy


@pytest.mark.parametrize("payload", [
    {}, {"fullName": None}, {"fullName": "  "}, {"division": "  "},
    {"fullName": "a" * 121}, {"division": "a" * 121}, {"role": "COACH"},
    {"email": "other@example.com"}, {"npm": "999999999"}, {"belt": "hitam"},
    {"beltTarget": "hitam"}, {"cameraDeviceId": "local-device"}, {"title": "Pelatih"},
    {"id": "999"},
])
def test_profile_whitelist_validation_is_atomic(client, member, payload):
    before = client.get("/api/v1/member/profile", headers=member).json()
    response = client.patch("/api/v1/member/profile", headers=member, json=payload)
    assert_domain_error(response, 422, "validation_error")
    assert client.get("/api/v1/member/profile", headers=member).json() == before


def test_profile_role_isolation_and_errors(client, member):
    assert_domain_error(client.get("/api/v1/member/profile"), 401, "unauthenticated")
    assert_domain_error(client.get("/api/v1/coach/profile", headers=member), 403, "forbidden_role")
    token = client.post("/api/v1/auth/sign-in", json={
        "identifier": "coach@example.com", "password": "password123",
    }).json()["accessToken"]
    headers = {"Authorization": "Bearer " + token}
    coach = client.get("/api/v1/coach/profile", headers=headers).json()
    assert coach["role"] == "coach" and coach["npm"] is None
    assert coach["statistics"]["completedSessionCount"] == 0 and coach["coach"] is None
    changed = client.patch("/api/v1/coach/profile", headers=headers,
                           json={"title": "  Pelatih UKM  ", "division": "UKM"})
    assert changed.status_code == 200 and changed.json()["title"] == "Pelatih UKM"
    assert client.patch("/api/v1/coach/profile", headers=headers, json={"title": None}).json()["title"] is None
    assert_domain_error(client.get("/api/v1/member/profile", headers=headers), 403, "forbidden_role")
    assert_domain_error(client.get("/api/v1/member/training-modules", headers=headers), 403, "forbidden_role")
    assert_domain_error(client.patch("/api/v1/member/profile", headers={**member, "Origin": "https://evil.example"},
                                    json={"fullName": "Attacker"}), 403, "origin_not_allowed")
    # Auth validation remains the original FastAPI contract.
    auth_error = client.post("/api/v1/auth/sign-in", json={})
    assert isinstance(auth_error.json()["detail"], list) and "code" not in auth_error.json()


def test_password_change_revokes_every_session_but_not_other_users(client):
    first, headers = signup(client)
    first_refresh = client.cookies.get("refresh_token")
    second = client.post("/api/v1/auth/sign-in", json={
        "identifier": "227006104", "password": "password123", "rememberMe": True,
    }).json()
    second_refresh = client.cookies.get("refresh_token")
    other, other_headers = signup(client, "other@example.com")
    assert jwt.decode(first["accessToken"], settings.jwt_secret, algorithms=["HS256"])["authVersion"] == 0
    response = client.patch("/api/v1/member/password", headers=headers, json={
        "currentPassword": "password123", "newPassword": "new-password123",
    })
    assert response.status_code == 204 and response.content == b""
    assert "Max-Age=0" in response.headers["set-cookie"]
    for access in [first["accessToken"], second["accessToken"]]:
        assert client.get("/api/v1/auth/session", headers={"Authorization": "Bearer " + access}).status_code == 401
    for token in [first_refresh, second_refresh]:
        client.cookies.clear()
        client.cookies.set("refresh_token", token, domain="testserver.local", path="/api/v1/auth")
        assert client.post("/api/v1/auth/refresh-session").status_code == 401
    assert client.get("/api/v1/auth/session", headers=other_headers).status_code == 200
    with database() as db:
        user = db.get(User, int(first["user"]["id"]))
        assert user.auth_version == 1 and user.password_changed_at is not None
        assert passwords.verify("new-password123", user.password_hash)
        assert all(row.revoked for row in db.scalars(select(RefreshToken).where(RefreshToken.user_id == user.id)))
    assert client.post("/api/v1/auth/sign-in", json={
        "identifier": "227006104", "password": "password123",
    }).status_code == 401
    login = client.post("/api/v1/auth/sign-in", json={
        "identifier": "227006104", "password": "new-password123", "rememberMe": True,
    })
    assert login.status_code == 200 and "Max-Age=604800" in login.headers["set-cookie"]
    assert jwt.decode(login.json()["accessToken"], settings.jwt_secret, algorithms=["HS256"])["authVersion"] == 1
    headers = {"Authorization": "Bearer " + login.json()["accessToken"]}
    assert client.get("/api/v1/member/profile", headers=headers).json()["passwordChangedAt"].endswith("Z")
    assert client.post("/api/v1/auth/refresh-session").status_code == 200


@pytest.mark.parametrize("current,new,status,code", [
    ("incorrect-password", "new-password123", 401, "invalid_current_password"),
    ("password123", "password123", 422, "password_unchanged"),
    ("password123", "short", 422, "validation_error"),
])
def test_failed_password_change_keeps_session(client, member, current, new, status, code):
    response = client.patch("/api/v1/member/password", headers=member,
                            json={"currentPassword": current, "newPassword": new})
    assert_domain_error(response, status, code)
    assert current not in response.text and new not in response.text
    assert client.get("/api/v1/auth/session", headers=member).status_code == 200
    assert client.post("/api/v1/auth/refresh-session").status_code == 200


def test_coach_password_and_legacy_version_transition(client):
    login = client.post("/api/v1/auth/login", json={"email": "coach@example.com", "password": "password123"}).json()
    claims = jwt.decode(login["access_token"], settings.jwt_secret, algorithms=["HS256"])
    del claims["authVersion"]
    legacy_token = jwt.encode(claims, settings.jwt_secret, algorithm="HS256")
    headers = {"Authorization": "Bearer " + legacy_token}
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 200
    assert_domain_error(client.patch("/api/v1/member/password", headers=headers,
                                    json={"currentPassword": "password123", "newPassword": "coach-new123"}),
                        403, "forbidden_role")
    assert client.patch("/api/v1/coach/password", headers=headers,
                        json={"currentPassword": "password123", "newPassword": "coach-new123"}).status_code == 204
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 401
    assert client.post("/api/v1/auth/login", json={"email": "coach@example.com", "password": "coach-new123"}).status_code == 200


@pytest.mark.parametrize("version", [None, "0", False, -1, 999])
def test_wrong_auth_version_rejected(client, member, version):
    token = member["Authorization"].removeprefix("Bearer ")
    claims = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    claims["authVersion"] = version
    headers = {"Authorization": "Bearer " + jwt.encode(claims, settings.jwt_secret, algorithm="HS256")}
    assert client.get("/api/v1/auth/session", headers=headers).status_code == 401


def test_catalog_empty_guidance_slug_and_config(client, member, monkeypatch):
    response = client.get("/api/v1/member/training-modules", headers=member)
    assert response.status_code == 200
    modules = response.json()["modules"]
    assert [m["slug"] for m in modules] == ["kuda-kuda", "pukulan", "tangkisan", "tendangan"]
    assert [m["order"] for m in modules] == [1, 2, 3, 4]
    for module in modules:
        assert module["capability"]["scoringAvailable"] is False
        assert module["capability"]["reason"] == "reference_not_ready"
        assert module["capability"]["repetitionCountingAvailable"] is False
        assert module["description"] is None and module["level"] is None
        prep = client.get(f'/api/v1/member/training-prep/{module["slug"]}', headers=member).json()
        assert prep["guides"] == [] and prep["checklist"] == []
    monkeypatch.setattr(settings, "max_video_mb", 20)
    monkeypatch.setattr(settings, "max_video_seconds", 15)
    config = client.get("/api/v1/member/record-config/kuda-kuda", headers=member).json()
    assert config == {"movementSlug": "kuda-kuda", "acceptedMimeTypes": ["video/mp4", "video/quicktime", "video/webm"],
                      "maxBytes": 20 * 1024 * 1024, "maxDurationSeconds": 15,
                      "retentionSeconds": 86400, "recommendedDurationSeconds": None}
    for slug in ["kuda_kuda", "unknown"]:
        assert_domain_error(client.get(f"/api/v1/member/training-prep/{slug}", headers=member), 404, "not_found")
    with database() as db:
        db.scalar(select(Movement).where(Movement.slug == "pukulan")).active = False
        db.commit()
    assert_domain_error(client.get("/api/v1/member/record-config/pukulan", headers=member), 404, "not_found")


def test_seed_preserves_curated_guidance_and_inactive_modules(client, member):
    guide = {"id": "guide-1", "text": "Panduan dari pelatih.", "source": "Catatan pelatih UKM"}
    with database() as db:
        row = db.scalar(select(Movement).where(Movement.slug == "pukulan"))
        row.description = "Panduan internal"
        row.guides = [guide, {"id": "bad", "text": "Tanpa sumber", "source": ""}]
        row.checklist = [guide]
        seed_movements(db)
        seed_movements(db)
        db.commit()
    prep = client.get("/api/v1/member/training-prep/pukulan", headers=member).json()
    assert prep["module"]["description"] == "Panduan internal"
    assert prep["guides"] == [guide] and prep["checklist"] == [guide]


@pytest.mark.parametrize("fault", ["malformed", "wrong_version", "partial", "zero_iqr", "nonfinite", "outside_root"])
def test_capability_only_uses_valid_reference_files(client, member, tmp_path, monkeypatch, fault):
    monkeypatch.setattr(settings, "reference_root", str(tmp_path))
    def profile(variant, version):
        return {"movement": "kuda_kuda", "variant": variant, "version": version,
                "feature_version": FEATURE_VERSION,
                "feature_statistics": {str(i): {"median": 10, "iqr": 2} for i in range(8)}}
    good = profile("good", "valid-v1")
    (tmp_path / "good.json").write_text(json.dumps(good), encoding="utf-8")
    bad = profile("bad", "bad-v1")
    if fault == "wrong_version":
        bad["feature_version"] = "unknown"
    elif fault == "partial":
        bad["provenance"] = {"debug_partial": True}
    elif fault == "zero_iqr":
        for value in bad["feature_statistics"].values():
            value["iqr"] = 0
    elif fault == "nonfinite":
        bad["feature_statistics"]["0"]["median"] = float("nan")
    (tmp_path / "bad.json").write_text("{" if fault == "malformed" else json.dumps(bad), encoding="utf-8")
    with database() as db:
        for variant, version, path in [("good", "valid-v1", "good.json"),
                                       ("bad", "bad-v1", "../outside.json" if fault == "outside_root" else "bad.json")]:
            db.add(ReferenceProfile(movement="kuda_kuda", variant=variant, version=version,
                                    artifact_path=path, evaluator_type="static-reference-pose"))
        db.commit()
    modules = client.get("/api/v1/member/training-modules", headers=member).json()["modules"]
    assert modules[0]["capability"]["scoringAvailable"] is True
    assert modules[0]["capability"]["referenceVersions"] == ["valid-v1"]
    assert modules[0]["capability"]["reason"] is None
    for module in modules[1:]:
        assert module["capability"]["scoringAvailable"] is False


def test_statistics_group_only_comparable_scores_and_owner(client, member):
    owner = int(client.get("/api/v1/auth/me", headers=member).json()["id"])
    def result(score, reference, feature=FEATURE_VERSION):
        return EvaluationSession(user_id=owner, movement="kuda_kuda", score=score,
                                 status="experimental" if score is not None else "reference_not_ready",
                                 analyzer_version="prototype-v1", reference_version=reference,
                                 result_json={"analysis": {"method": "static-reference-pose"},
                                              "model": {"feature_version": feature}})
    with database() as db:
        db.add_all([result(80, "v1"), result(60, "v1"), result(90, "v1", None),
                    result(None, None), result(100, "v2")])
        other = result(0, "v1")
        other.user_id = db.scalar(select(User.id).where(User.email == "coach@example.com"))
        db.add(other)
        db.commit()
    stats = client.get("/api/v1/member/profile", headers=member).json()["statistics"]
    assert stats["completedSessionCount"] == 5 and stats["scoredSessionCount"] == 4
    assert stats["excludedScoreCount"] == 2 and stats["durationSampleCount"] == 0
    assert [(g["referenceVersion"], g["averageScore"], g["sampleCount"])
            for g in stats["similarityGroups"]] == [("v1", 70, 2), ("v2", 100, 1)]
    assert client.get("/api/v1/member/training-modules", headers=member).json()["statistics"] == stats


def test_openapi_new_routes_and_auth_shapes(client):
    spec = client.get("/openapi.json").json()
    assert spec["paths"]["/api/v1/member/profile"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]["$ref"].endswith("ProfileOut")
    assert "204" in spec["paths"]["/api/v1/coach/password"]["patch"]["responses"]
    assert "404" in spec["paths"]["/api/v1/member/training-prep/{slug}"]["get"]["responses"]
    assert set(spec["components"]["schemas"]["AuthTokens"]["properties"]) == {"user", "accessToken", "expiresIn"}
