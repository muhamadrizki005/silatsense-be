from contextlib import contextmanager
from datetime import datetime, timedelta
import json
from uuid import uuid4

import pytest
from sqlalchemy import event, select

from app.core.config import settings
from app.db.session import get_db
from app.main import app
from app.models.entities import CoachNote, EvaluationSession, MediaAsset, Movement, TrainingSession, User
from app.repositories.evaluations import EvaluationRepository
from test_sessions_jobs import analysis_result


@pytest.fixture
def history_data(client, member, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "media_root", str(tmp_path / "private"))
    monkeypatch.setattr("app.services.history.now", lambda: datetime(2026, 10, 18, 12))
    factory = contextmanager(app.dependency_overrides[get_db])
    owner = int(client.get("/api/v1/auth/me", headers=member).json()["id"])
    def create(*, movement="pukulan", state="completed", created=None, completed=None,
               score=None, feature_version="image-plane-v1", reference_version="ref-v1",
               method="static-reference-pose", duration=None, deleted=False, user_id=None):
        created = created or datetime(2026, 10, 14, 12)
        with factory() as db:
            session = TrainingSession(user_id=user_id or owner, movement=movement,
                processing_status=state, created_at=created,
                completed_at=(completed or created) if state in {"completed", "failed"} else None,
                deleted_at=created if deleted else None)
            db.add(session)
            db.flush()
            if state == "completed":
                data = analysis_result()
                data.update(movement=movement, score=score, status="experimental" if score is not None else "reference_not_ready")
                data["model"].update(feature_version=feature_version, reference_version=reference_version)
                data["analysis"]["method"] = method
                row = EvaluationRepository(db).build(session.user_id, data, session.id)
                row.created_at = session.completed_at
            if duration is not None:
                db.add(MediaAsset(session_id=session.id, user_id=session.user_id,
                    storage_key=f"objects/{uuid4().hex}.mp4", mime_type="video/mp4", byte_size=1,
                    checksum="0" * 64, duration_seconds=duration, width=64, height=64,
                    expires_at=datetime(2026, 1, 1)))
            db.commit()
            return session.id
    return create, factory, owner


def test_empty_history_dashboard_defaults_and_no_store(client, member, history_data):
    history = client.get("/api/v1/member/history", headers=member)
    assert history.status_code == 200, history.text
    assert history.json() == {"items": [], "nextCursor": None}
    response = client.get("/api/v1/member/dashboard", headers=member)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["statistics"] == dict(completedSessionCount=0, totalDurationSeconds=0,
        durationSampleCount=0, scoredSessionCount=0, excludedScoreCount=0, similarityGroups=[])
    assert data["lastSession"] is data["latestCoachNote"] is data["coach"] is data["dominantMovementSlug"] is None
    assert data["timezone"] == "Asia/Jakarta"
    assert [day["date"] for day in data["weeklyActivity"]] == [f"2026-10-{date}" for date in range(12, 19)]
    assert all(day["sessionCount"] == day["durationSeconds"] == 0 for day in data["weeklyActivity"])
    for result in (history, response):
        assert result.headers["cache-control"] == "no-store" and result.headers["x-request-id"]


def test_cursor_same_timestamp_limit_defaults_and_page_size_change(client, member, history_data):
    create, _, _ = history_data
    ids = [create(state="queued") for _ in range(24)]
    first = client.get("/api/v1/member/history", headers=member).json()
    assert [int(row["session"]["id"]) for row in first["items"]] == list(reversed(ids))[:20]
    assert first["nextCursor"]
    second = client.get("/api/v1/member/history", headers=member,
        params={"cursor": first["nextCursor"], "limit": 3}).json()
    assert [int(row["session"]["id"]) for row in second["items"]] == list(reversed(ids))[20:23]
    last = client.get("/api/v1/member/history", headers=member,
        params={"cursor": second["nextCursor"], "limit": 3}).json()
    assert int(last["items"][0]["session"]["id"]) == ids[0] and last["nextCursor"] is None


def test_cursor_rechecks_deletion_and_does_not_repeat_after_new_insert(client, member, history_data):
    create, factory, _ = history_data
    ids = [create(state="queued") for _ in range(4)]
    page = client.get("/api/v1/member/history", headers=member, params={"limit": 2}).json()
    assert client.delete(f"/api/v1/member/sessions/{ids[2]}", headers=member).status_code == 204
    create(state="queued", created=datetime(2026, 10, 19))
    with factory() as db:
        db.get(TrainingSession, ids[1]).deleted_at = datetime(2026, 10, 18)
        db.commit()
    response = client.get("/api/v1/member/history", headers=member,
        params={"limit": 2, "cursor": page["nextCursor"]})
    assert response.status_code == 200
    assert [int(row["session"]["id"]) for row in response.json()["items"]] == [ids[0]]


def test_cursor_bound_to_owner_filters_signature_and_key(client, member, history_data, monkeypatch):
    create, _, _ = history_data
    for _ in range(2):
        create()
    cursor = client.get("/api/v1/member/history", headers=member, params={"limit": 1}).json()["nextCursor"]
    other = client.post("/api/v1/auth/sign-up", json={
        "fullName": "Other Member", "identifier": "history-other@example.com", "password": "password123"}).json()
    headers = {"Authorization": "Bearer " + other["accessToken"]}
    attempts = [(headers, {"cursor": cursor}), (member, {"cursor": cursor, "movementSlug": "pukulan"}),
                (member, {"cursor": cursor, "processingStatus": "completed"}),
                (member, {"cursor": cursor, "reviewStatus": "pending"}),
                (member, {"cursor": cursor, "from": "2026-01-01T00:00:00Z"}),
                (member, {"cursor": cursor[:10] + ("A" if cursor[10] != "A" else "B") + cursor[11:]}),
                (member, {"cursor": ""}), (member, {"cursor": "not-a-cursor"}),
                (member, {"cursor": "x" * 4097})]
    for auth, params in attempts:
        result = client.get("/api/v1/member/history", headers=auth, params=params)
        assert result.status_code == 422, result.text
        assert result.json()["code"] == "invalid_cursor"
    from app.core.cursors import decode_cursor
    from app.schemas.history import HistoryQuery
    monkeypatch.setattr(settings, "jwt_secret", "rotated-local-test-key")
    from app.core.errors import DomainError
    with pytest.raises(DomainError) as failure:
        decode_cursor(cursor, 2, HistoryQuery().cursor_filters())
    assert failure.value.code == "invalid_cursor"


@pytest.mark.parametrize("params", [
    {"limit": 0}, {"limit": 101}, {"limit": "bad"}, {"movementSlug": "kuda_kuda"},
    {"processingStatus": "done"}, {"reviewStatus": "accepted"}, {"offset": 20},
    {"from": "2026-10-18"}, {"from": "1690000000"}, {"from": "2026-10-18T00:00:00"},
    {"from": "2026-10-18T00:00:00+07:00"}, {"from": "2026-13-18T00:00:00Z"},
    {"from": "2026-10-18T00:00:00Z", "to": "2026-10-18T00:00:00Z"},
    {"from": "2026-10-19T00:00:00Z", "to": "2026-10-18T00:00:00Z"},
])
def test_invalid_history_queries_use_domain_errors(client, member, history_data, params):
    result = client.get("/api/v1/member/history", headers=member, params=params)
    assert result.status_code == 422, result.text
    assert result.json()["code"] == "validation_error" and result.json()["requestId"]


def test_filters_public_slug_utc_inclusive_exclusive_and_no_review_yet(client, member, history_data):
    create, _, _ = history_data
    start, end = datetime(2026, 10, 14, 12), datetime(2026, 10, 15, 12)
    kept = create(movement="kuda_kuda", created=start)
    create(movement="kuda_kuda", created=start - timedelta(microseconds=1))
    create(movement="kuda_kuda", created=end)
    create(movement="pukulan", created=start)
    create(movement="kuda_kuda", state="failed", created=start)
    create(movement="kuda_kuda", created=start, deleted=True)
    response = client.get("/api/v1/member/history", headers=member, params={
        "movementSlug": "kuda-kuda", "processingStatus": "completed", "reviewStatus": "pending",
        "from": "2026-10-14T12:00:00Z", "to": "2026-10-15T12:00:00+00:00"})
    assert response.status_code == 200, response.text
    assert [row["session"]["id"] for row in response.json()["items"]] == [str(kept)]
    for review in ("approved", "needs_revision"):
        assert client.get("/api/v1/member/history", headers=member, params={"reviewStatus": review}).json()["items"] == []


def test_history_all_processing_states_detail_nulls_and_legacy(client, member, history_data):
    create, _, _ = history_data
    ids = {state: create(state=state) for state in ("queued", "processing", "failed", "completed")}
    for state, sid in ids.items():
        response = client.get(f"/api/v1/member/history/{sid}", headers=member)
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["session"]["processingStatus"] == state
        assert data["coach"] is data["review"] is None
        assert data["followUpTasks"] == data["reviewHistory"] == data["legacyNotes"] == []
        if state == "completed":
            assert data["evaluation"]["score"] is None and data["session"]["media"]["status"] == "unavailable"
            assert data["session"]["uploadedAt"] is None and data["evaluation"]["sessionId"] == str(sid)
        else:
            assert data["evaluation"] is None
    page = client.get("/api/v1/member/history", headers=member).json()
    assert len(page["items"]) == 4
    assert {row["scoreReason"] for row in page["items"]} == {"evaluation_pending", "analysis_failed", "reference_not_ready"}


def test_statistics_group_versions_categories_samples_and_no_global_average(client, member, history_data):
    create, _, _ = history_data
    create(score=60, duration=10)
    create(score=80, duration=20)
    create(score=100, reference_version="ref-v2")
    create(score=20, movement="tangkisan")
    create(score=40, feature_version="features-v2")
    create(score=30, feature_version=None)
    create(score=None)
    create(score=99, deleted=True, duration=100)
    create(state="queued", duration=100)
    create(state="failed", duration=100)
    dashboard = client.get("/api/v1/member/dashboard", headers=member)
    assert dashboard.status_code == 200, dashboard.text
    statistics = dashboard.json()["statistics"]
    assert statistics["completedSessionCount"] == 7
    assert statistics["totalDurationSeconds"] == 30 and statistics["durationSampleCount"] == 2
    assert statistics["scoredSessionCount"] == 6 and statistics["excludedScoreCount"] == 2
    groups = statistics["similarityGroups"]
    assert len(groups) == 4
    same = next(row for row in groups if row["movementSlug"] == "pukulan" and row["referenceVersion"] == "ref-v1"
                and row["featureVersion"] == "image-plane-v1")
    assert same["averageScore"] == 70 and same["sampleCount"] == 2
    assert "averageScore" not in statistics
    assert client.get("/api/v1/member/profile", headers=member).json()["statistics"] == statistics
    assert client.get("/api/v1/member/training-modules", headers=member).json()["statistics"] == statistics


def test_zero_score_is_a_sample_and_method_analyzer_versions_are_separate(client, member, history_data):
    create, factory, _ = history_data
    create(score=0)
    create(score=60, method="historical-method")
    older = create(score=20)
    with factory() as db:
        db.scalar(select(EvaluationSession).where(EvaluationSession.training_session_id == older)).analyzer_version = "prototype-v0"
        db.commit()
    data = client.get("/api/v1/member/dashboard", headers=member).json()["statistics"]
    assert data["scoredSessionCount"] == 3 and data["excludedScoreCount"] == 0
    assert len(data["similarityGroups"]) == 3
    assert sorted(row["averageScore"] for row in data["similarityGroups"]) == [0, 20, 60]
    assert all(row["sampleCount"] == 1 for row in data["similarityGroups"])


def test_last_session_uses_completed_time_and_dominant_tie_uses_catalog(client, member, history_data):
    create, factory, _ = history_data
    create(movement="pukulan", created=datetime(2026, 10, 18), completed=datetime(2026, 10, 18, 1))
    chosen = create(movement="kuda_kuda", created=datetime(2026, 10, 12), completed=datetime(2026, 10, 18, 2))
    create(state="failed", created=datetime(2026, 10, 18, 4))
    data = client.get("/api/v1/member/dashboard", headers=member).json()
    assert data["lastSession"]["session"]["id"] == str(chosen)
    assert data["dominantMovementSlug"] == "kuda-kuda"
    with factory() as db:
        row = db.scalar(select(Movement).where(Movement.slug == "pukulan"))
        row.display_order = -1
        db.commit()
    assert client.get("/api/v1/member/dashboard", headers=member).json()["dominantMovementSlug"] == "pukulan"


@pytest.mark.parametrize("utc_now,monday", [(datetime(2026, 10, 18, 16, 59, 59), "2026-10-12"),
                                          (datetime(2026, 10, 18, 17), "2026-10-19")])
def test_jakarta_monday_boundary_utc_now(client, member, history_data, monkeypatch, utc_now, monday):
    monkeypatch.setattr("app.services.history.now", lambda: utc_now)
    data = client.get("/api/v1/member/dashboard", headers=member).json()
    assert data["weeklyActivity"][0]["date"] == monday


def test_weekly_completed_time_exact_boundaries_and_verified_duration(client, member, history_data):
    create, _, _ = history_data
    start = datetime(2026, 10, 11, 17)
    create(created=start, completed=start, duration=4)
    create(created=start, completed=start - timedelta(microseconds=1), duration=50)
    create(created=start, completed=start + timedelta(hours=24), duration=6)
    create(created=start, completed=start + timedelta(days=7), duration=100)
    create(created=start, completed=start + timedelta(days=6, hours=23), duration=None)
    create(created=start, completed=start, duration=100, deleted=True)
    create(state="failed", completed=start, duration=100)
    data = client.get("/api/v1/member/dashboard", headers=member).json()
    assert [day["sessionCount"] for day in data["weeklyActivity"]] == [1, 1, 0, 0, 0, 0, 1]
    assert [day["durationSeconds"] for day in data["weeklyActivity"]] == [4, 6, 0, 0, 0, 0, 0]


def test_notes_preserve_author_latest_tie_and_exclude_deleted(client, member, history_data):
    create, factory, owner = history_data
    sid, deleted = create(), create(deleted=True)
    with factory() as db:
        old_coach = db.scalar(select(User).where(User.role == "COACH"))
        evaluations = {row.training_session_id: row.id for row in db.scalars(select(EvaluationSession))}
        for session_id, text in ((sid, "First"), (sid, "Second"), (deleted, "Hidden")):
            db.add(CoachNote(evaluation_id=evaluations[session_id], coach_id=old_coach.id,
                note=text, created_at=datetime(2026, 10, 18)))
        db.commit()
        coach_id = str(old_coach.id)
    data = client.get(f"/api/v1/member/history/{sid}", headers=member).json()
    assert [note["text"] for note in data["legacyNotes"]] == ["First", "Second"]
    assert all(note["author"]["id"] == coach_id and note["publishedAt"].endswith("Z") for note in data["legacyNotes"])
    dashboard = client.get("/api/v1/member/dashboard", headers=member).json()
    assert dashboard["latestCoachNote"]["text"] == "Second" and dashboard["coach"] is None
    assert client.delete(f"/api/v1/member/sessions/{sid}", headers=member).status_code == 204
    assert client.get("/api/v1/member/dashboard", headers=member).json()["latestCoachNote"] is None


def test_owner_role_deleted_and_invalid_id_protection(client, member, history_data):
    create, _, _ = history_data
    sid = create(score=90)
    other = client.post("/api/v1/auth/sign-up", json={
        "fullName": "Another Member", "identifier": "isolation@example.com", "password": "password123"}).json()
    auth = {"Authorization": "Bearer " + other["accessToken"]}
    assert client.get("/api/v1/member/history", headers=auth).json()["items"] == []
    assert client.get("/api/v1/member/dashboard", headers=auth).json()["statistics"]["completedSessionCount"] == 0
    assert client.get(f"/api/v1/member/history/{sid}", headers=auth).status_code == 404
    coach = client.post("/api/v1/auth/login", json={"email": "coach@example.com", "password": "password123"}).json()
    coach_auth = {"Authorization": "Bearer " + coach["access_token"]}
    for path in ("/api/v1/member/history", "/api/v1/member/dashboard", f"/api/v1/member/history/{sid}"):
        assert client.get(path).status_code == 401
        assert client.get(path, headers=coach_auth).status_code == 403
    assert client.get("/api/v1/member/history/bad", headers=member).status_code == 404
    assert client.delete(f"/api/v1/member/sessions/{sid}", headers=member).status_code == 204
    assert client.get(f"/api/v1/member/history/{sid}", headers=member).status_code == 404
    assert client.get("/api/v1/member/history", headers=member).json()["items"] == []


def test_history_related_queries_are_batched_and_private_paths_absent(client, member, history_data):
    create, factory, _ = history_data
    for _ in range(25):
        create(duration=10)
    with factory() as db:
        engine = db.get_bind()
    queries = []
    def before_execute(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            queries.append(statement)
    event.listen(engine, "before_cursor_execute", before_execute)
    try:
        result = client.get("/api/v1/member/history", headers=member, params={"limit": 100})
    finally:
        event.remove(engine, "before_cursor_execute", before_execute)
    assert result.status_code == 200 and len(result.json()["items"]) == 25
    assert len(queries) <= 8  # auth/page + batched evaluations/media/catalog/reviews/assignments.
    assert "storage_key" not in result.text and "objects/" not in result.text
    assert all(row["session"]["media"]["status"] == "expired" for row in result.json()["items"])
