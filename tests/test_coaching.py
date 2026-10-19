from contextlib import contextmanager
from datetime import timedelta
import io
import os
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.core.security import passwords
from app.db.session import get_db
from app.main import app
from app.models.entities import AssignmentEvent, CoachAssignment, FeedbackDraft, FollowUpTask, IdempotencyRecord, MediaAsset, ReviewRevision, TrainingSession, User, now
from helpers import save_completed_evaluation
from app.services.assignments import assign_coach
from app.services.media import stream_chunks
from test_sessions_jobs import analysis_result


@pytest.fixture
def coaching(client, member, tmp_path, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "media_root", str(tmp_path))
    factory = contextmanager(app.dependency_overrides[get_db])
    owner = int(client.get("/api/v1/auth/session", headers=member).json()["id"])
    coach = client.post("/api/v1/auth/sign-in", json={"identifier": "coach@example.com", "password": "password123"}).json()
    with factory() as db:
        second = User(name="Second Coach", email="second@example.com", role="COACH", password_hash=passwords.hash("password123"))
        db.add(second)
        db.commit()
        second_id = second.id
        row = save_completed_evaluation(db, owner, analysis_result())
        sid, eid = row.training_session_id, row.id
    auth2 = client.post("/api/v1/auth/sign-in", json={"identifier": "second@example.com", "password": "password123"}).json()
    return dict(factory=factory, owner=owner, sid=sid, eid=eid, first=int(coach["user"]["id"]), second=second_id,
        coach={"Authorization": "Bearer " + coach["accessToken"]}, coach2={"Authorization": "Bearer " + auth2["accessToken"]})


def assign(ctx, coach=None):
    with ctx["factory"]() as db:
        return assign_coach(db, ctx["owner"], ctx["first"] if coach is None else coach, "test-admin", "Test assignment")


def draft(client, ctx, auth=None, version=0, decision="needs_revision", tasks=True):
    return client.put(f"/api/v1/coach/sessions/{ctx['sid']}/feedback-draft", headers=auth or ctx["coach"], json={
        "expectedVersion": version, "decision": decision, "note": "  Perbaiki posisi  ",
        "bodyAssessments": [{"bodyPart": "left_knee", "status": "needs_revision", "note": " Periksa lutut "}],
        "tasks": [{"instruction": " Latihan ulang "}] if tasks else []})


def publish(client, ctx, auth=None, revision=0, version=1, key="review-1"):
    return client.post(f"/api/v1/coach/sessions/{ctx['sid']}/reviews",
        headers={**(auth or ctx["coach"]), "Idempotency-Key": key},
        json={"expectedRevision": revision, "expectedDraftVersion": version})


def test_unassigned_coach_cannot_read_private_objects(client, member, coaching):
    c = coaching
    paths = [f"/api/v1/coach/roster/{c['owner']}", f"/api/v1/coach/roster/{c['owner']}/sessions",
        f"/api/v1/coach/sessions/{c['sid']}", f"/api/v1/coach/sessions/{c['sid']}/pose",
        f"/api/v1/coach/sessions/{c['sid']}/video"]
    for path in paths:
        result=client.get(path, headers=c["coach"])
        assert result.status_code == 404, path
        assert result.headers["cache-control"] == "no-store"
    assert client.get("/api/v1/coach/roster", headers=c["coach"]).json() == {"items": [], "nextCursor": None}
    empty = client.get("/api/v1/coach/overview", headers=c["coach"])
    assert empty.status_code == 200, empty.text
    assert empty.json()["memberCount"] == empty.json()["reviewQueueCount"] == 0
    assert empty.json()["recentSessions"] == empty.json()["topIssues"] == []
    assert draft(client, c).status_code == 404 and publish(client, c).status_code == 404
    profile = client.get("/api/v1/member/profile", headers=member).json()
    assert profile["coach"] is None
    assert client.get(f"/api/v1/member/history/{c['sid']}", headers=member).status_code == 200


def test_assignment_transfer_revoke_and_unique_member_history(client, member, coaching):
    c = coaching
    assert assign(c)
    assert assign(c) is None
    assert client.get("/api/v1/member/profile", headers=member).json()["coach"]["id"] == str(c["first"])
    assert client.get("/api/v1/coach/profile",headers=c["coach"]).json()["statistics"]["completedSessionCount"] == 1
    assert client.get(f"/api/v1/coach/roster/{c['owner']}", headers=c["coach"]).status_code == 200
    assign(c, c["second"])
    assert client.get("/api/v1/coach/profile",headers=c["coach"]).json()["statistics"]["completedSessionCount"] == 0
    assert client.get(f"/api/v1/coach/sessions/{c['sid']}", headers=c["coach"]).status_code == 404
    assert client.get(f"/api/v1/coach/sessions/{c['sid']}", headers=c["coach2"]).status_code == 200
    with c["factory"]() as db:
        assign_coach(db, c["owner"], None, "test-admin", "Revoked")
    assert client.get("/api/v1/member/profile", headers=member).json()["coach"] is None
    assert client.get(f"/api/v1/coach/sessions/{c['sid']}", headers=c["coach2"]).status_code == 404
    with c["factory"]() as db:
        assert db.scalar(select(func.count()).select_from(CoachAssignment)) == 0
        events = db.scalars(select(AssignmentEvent).order_by(AssignmentEvent.id)).all()
        assert [(r.from_coach_id, r.to_coach_id) for r in events] == [(None,c["first"]),(c["first"],c["second"]),(c["second"],None)]


def test_publish_snapshot_replay_revision_tasks_and_member_visibility(client, member, coaching):
    c = coaching
    assign(c)
    saved = draft(client, c)
    assert saved.status_code == 200, saved.text
    assert saved.json()["note"] == "Perbaiki posisi" and saved.json()["version"] == 1
    assert client.get(f"/api/v1/member/history/{c['sid']}", headers=member).json()["review"] is None
    first = publish(client, c)
    assert first.status_code == 201, first.text
    assert publish(client, c).json() == first.json()
    assert publish(client, c, version=2).status_code == 409
    history = client.get(f"/api/v1/member/history/{c['sid']}", headers=member).json()
    assert history["review"] == first.json() and len(history["followUpTasks"]) == 1
    assert history["legacyNotes"] == [] and history["session"]["reviewStatus"] == "needs_revision"
    assert history["session"]["reviewAvailable"] is True
    assert client.get(f"/api/v1/coach/sessions/{c['sid']}", headers=c["coach"]).json()["feedbackDraft"] is None
    assert draft(client, c, decision="approved").status_code == 200
    revised = publish(client, c, revision=1, key="review-2")
    assert revised.status_code == 201, revised.text
    assert revised.json()["revision"] == 2 and revised.json()["supersedesReviewId"] == first.json()["id"]
    history = client.get(f"/api/v1/member/history/{c['sid']}", headers=member).json()
    assert history["reviewHistory"] == [first.json(), revised.json()] and len(history["followUpTasks"]) == 2
    assert history["evaluation"]["score"] is None and history["session"]["reviewStatus"] == "approved"
    assert client.get("/api/v1/member/history", headers=member, params={"reviewStatus":"approved"}).json()["items"][0]["review"] == revised.json()
    assert client.get("/api/v1/member/history", headers=member, params={"reviewStatus":"pending"}).json()["items"] == []
    dashboard = client.get("/api/v1/member/dashboard", headers=member).json()
    assert dashboard["latestCoachNote"]["text"] == revised.json()["note"] and dashboard["coach"]["id"] == str(c["first"])


def test_transfer_archives_draft_even_when_same_coach_returns(client, member, coaching):
    c = coaching
    assign(c)
    assert draft(client, c).status_code == 200
    assign(c, c["second"])
    assert draft(client, c, version=1).status_code == 404
    assert client.get(f"/api/v1/coach/sessions/{c['sid']}", headers=c["coach2"]).json()["feedbackDraft"] is None
    assign(c, c["first"])
    assert client.get(f"/api/v1/coach/sessions/{c['sid']}", headers=c["coach"]).json()["feedbackDraft"] is None
    assert draft(client, c).status_code == 200
    with c["factory"]() as db:
        assert db.scalar(select(func.count()).select_from(FeedbackDraft)) == 2


def test_new_coach_can_revise_old_review_author_is_preserved(client, member, coaching):
    c = coaching
    assign(c)
    draft(client, c)
    first = publish(client, c).json()
    assign(c, c["second"])
    assert publish(client, c).status_code == 404  # Idempotency cannot bypass revocation.
    assert draft(client, c, auth=c["coach2"], decision="approved").status_code == 200
    second = publish(client, c, auth=c["coach2"], revision=1, key="new-coach")
    assert second.status_code == 201, second.text
    history = client.get(f"/api/v1/member/history/{c['sid']}", headers=member).json()
    assert [row["author"]["id"] for row in history["reviewHistory"]] == [str(c["first"]), str(c["second"])]
    assert history["reviewHistory"][0] == first


def test_conflicts_and_decision_required_do_not_publish_partial_data(client, member, coaching):
    c = coaching
    assign(c)
    assert draft(client, c, decision=None).status_code == 200
    assert draft(client, c).status_code == 409
    assert publish(client, c).status_code == 422
    assert publish(client, c, revision=3).status_code == 409
    assert draft(client, c, version=1).status_code == 200
    assert publish(client, c, version=1).status_code == 409
    with c["factory"]() as db:
        assert db.scalar(select(func.count()).select_from(ReviewRevision)) == 0
        assert db.scalar(select(func.count()).select_from(FollowUpTask)) == 0
        assert db.scalar(select(func.count()).select_from(IdempotencyRecord)) == 0


@pytest.mark.parametrize("payload", [
    {"expectedVersion":0,"note":"x"*5001}, {"expectedVersion":0,"author":{"id":"999"}},
    {"expectedVersion":0,"tasks":[{"instruction":" "}]},
    {"expectedVersion":0,"bodyAssessments":[{"bodyPart":"knee","status":"approved"}]*2},
    {"expectedVersion":0,"bodyAssessments":[{"bodyPart":" ","status":"approved"}]},
    {"expectedVersion":0,"tasks":[{"instruction":"x"}]*21},
    {"expectedVersion":-1}, {"expectedVersion":0,"decision":"correct"},
])
def test_invalid_draft_payload_rejected(client, member, coaching, payload):
    assign(coaching)
    response = client.put(f"/api/v1/coach/sessions/{coaching['sid']}/feedback-draft", headers=coaching["coach"], json=payload)
    assert response.status_code == 422 and response.json()["code"] == "validation_error"


def test_follow_up_tasks_owner_only_and_retry_without_coach(client, member, coaching):
    c = coaching
    path = f"/api/v1/member/sessions/{c['sid']}/follow-ups"
    response = client.post(path, headers={**member,"Idempotency-Key":"retry"}, json={"intent":"retry"})
    assert response.status_code == 201, response.text
    assert client.post(path, headers={**member,"Idempotency-Key":"retry"}, json={"intent":"retry"}).json() == response.json()
    assign(c)
    draft(client,c)
    review = publish(client,c).json()
    tid = review["taskIds"][0]
    other = client.post("/api/v1/auth/sign-up", json={"fullName":"Other Member","identifier":"tasks@example.com","password":"password123"}).json()
    auth = {"Authorization":"Bearer "+other["accessToken"]}
    assert client.patch(f"/api/v1/member/follow-up-tasks/{tid}", headers=auth,json={"status":"completed"}).status_code == 404
    result = client.patch(f"/api/v1/member/follow-up-tasks/{tid}", headers=member,json={"status":"completed"})
    assert result.status_code == 200, result.text
    assert client.patch(f"/api/v1/member/follow-up-tasks/{tid}", headers=member,json={"status":"completed"}).json() == result.json()
    assert client.patch(f"/api/v1/member/follow-up-tasks/{tid}", headers=member,json={"instruction":"tamper"}).status_code == 422
    assert client.delete(f"/api/v1/member/sessions/{c['sid']}", headers=member).status_code == 204
    assert client.patch(f"/api/v1/member/follow-up-tasks/{tid}", headers=member,json={"status":"dismissed"}).status_code == 404
    assert client.post(path, headers={**member,"Idempotency-Key":"retry"},json={"intent":"retry"}).status_code == 404


def test_roster_search_cursor_scope_overview_queue_and_issue_counts(client, member, coaching):
    c = coaching
    assign(c)
    roster = client.get("/api/v1/coach/roster", headers=c["coach"], params={"q":" one@ "})
    assert roster.status_code == 200, roster.text
    assert roster.json()["items"][0]["profile"]["id"] == str(c["owner"])
    assert client.get("/api/v1/coach/roster",headers=c["coach"],params={"q":"%"}).json()["items"] == []
    assert client.get(f"/api/v1/coach/roster/{c['owner']}/sessions",headers=c["coach"]).status_code == 200
    assert client.get("/api/v1/coach/overview",headers=c["coach"]).json()["reviewQueueCount"] == 1
    draft(client,c)
    publish(client,c)
    overview = client.get("/api/v1/coach/overview",headers=c["coach"])
    assert overview.status_code == 200, overview.text
    assert overview.json()["reviewQueueCount"] == 0 and overview.json()["statistics"]["completedSessionCount"] == 1


def test_coach_range_stream_stops_on_transfer(client, member, coaching, monkeypatch):
    c = coaching
    assign(c)
    from app.services.storage import LocalStorage
    key = f"objects/{uuid4().hex}.mp4"
    with LocalStorage().create(key) as target:
        target.write(b"1234567890")
    with c["factory"]() as db:
        media = MediaAsset(session_id=c["sid"],user_id=c["owner"],storage_key=key,mime_type="video/mp4",
            byte_size=10,checksum="0"*64,duration_seconds=1,width=10,height=10,expires_at=now()+timedelta(hours=1))
        db.add(media)
        db.commit()
        aid, expiry = media.id,media.expires_at
        generation = db.get(CoachAssignment,c["owner"]).event_id
    path=f"/api/v1/coach/sessions/{c['sid']}/video"
    response=client.get(path,headers={**c["coach"],"Range":"bytes=-4"})
    assert response.status_code == 206 and response.content == b"7890", response.text
    monkeypatch.setattr("app.services.media.CHUNK_SIZE",4)
    handle=io.BytesIO(b"1234567890")
    stream=stream_chunks(handle,0,9,c["factory"],c["owner"],0,c["sid"],aid,expiry,c["first"],generation)
    assert next(stream) == b"1234"
    assign(c,c["second"])
    assert list(stream) == [] and handle.closed
    assert client.get(path,headers=c["coach"]).status_code == 404
    assert client.get(path,headers=c["coach2"]).status_code == 200


def test_immutable_review_and_assignment_event_orm_protection(client, member, coaching):
    c=coaching
    assign(c)
    draft(client,c)
    assert publish(client,c).status_code == 201
    for table,field,value in ((ReviewRevision,"decision","approved"),(AssignmentEvent,"reason","tampered")):
        with c["factory"]() as db:
            row=db.scalar(select(table))
            setattr(row,field,value)
            with pytest.raises(ValueError,match="immutable"):
                db.commit()


def test_publish_failure_rolls_back_review_tasks_head_and_keeps_draft(client, member, coaching, monkeypatch):
    c=coaching
    assign(c)
    draft(client,c)
    from sqlalchemy.orm import Session
    from app.models.entities import ReviewHead
    original=Session.commit
    def fail_commit(db):
        if any(isinstance(row,ReviewHead) for row in db.new):
            raise RuntimeError("Simulated commit failure")
        return original(db)
    monkeypatch.setattr(Session,"commit",fail_commit)
    assert publish(client,c).status_code == 500
    with c["factory"]() as db:
        for table in (ReviewRevision,FollowUpTask,ReviewHead,IdempotencyRecord):
            assert db.scalar(select(func.count()).select_from(table)) == 0
        assert db.scalar(select(func.count()).select_from(FeedbackDraft)) == 1


def test_blank_note_is_null_and_published_decision_needs_no_dummy_note(client, member, coaching):
    c=coaching
    assign(c)
    response=client.put(f"/api/v1/coach/sessions/{c['sid']}/feedback-draft",headers=c["coach"],
        json={"expectedVersion":0,"decision":"approved","note":"   "})
    assert response.status_code == 200 and response.json()["note"] is None
    assert publish(client,c).status_code == 201
    dashboard=client.get("/api/v1/member/dashboard",headers=member)
    assert dashboard.status_code == 200,dashboard.text
    assert dashboard.json()["latestCoachNote"] is None


@pytest.mark.parametrize("state",["queued","processing","failed"])
def test_retry_terminal_rules_and_publish_requires_completed(client, member, coaching, state):
    c=coaching
    assign(c)
    with c["factory"]() as db:
        db.get(TrainingSession,c["sid"]).processing_status=state
        db.commit()
    assert draft(client,c).status_code == 200
    assert publish(client,c).status_code == 409
    retry=client.post(f"/api/v1/member/sessions/{c['sid']}/follow-ups",headers={**member,"Idempotency-Key":"retry"},json={"intent":"retry"})
    assert retry.status_code == (201 if state == "failed" else 409)
    if state != "failed":
        assert retry.json()["code"] == "session_not_terminal"


def test_roster_cursor_is_coach_and_query_bound(client, member, coaching):
    c=coaching
    assign(c)
    for index in range(2):
        user=client.post("/api/v1/auth/sign-up",json={"fullName":f"New Member {index}","identifier":f"roster{index}@example.com","password":"password123"}).json()
        with c["factory"]() as db:
            assign_coach(db,int(user["user"]["id"]),c["first"],"admin","Roster pagination")
    response=client.get("/api/v1/coach/roster",headers=c["coach"],params={"limit":1})
    assert response.status_code == 200,response.text
    page=response.json()
    cursor=page["nextCursor"]
    assert client.get("/api/v1/coach/roster",headers=c["coach2"],params={"cursor":cursor}).status_code == 422
    assert client.get("/api/v1/coach/roster",headers=c["coach"],params={"cursor":cursor,"q":"New"}).status_code == 422
    tail=client.get("/api/v1/coach/roster",headers=c["coach"],params={"cursor":cursor,"limit":100}).json()
    ids=[page["items"][0]["profile"]["id"]]+[row["profile"]["id"] for row in tail["items"]]
    assert len(set(ids)) == len(ids) == 3 and tail["nextCursor"] is None


def test_overview_top_issues_distinct_sessions_and_tie_limit(client, member, coaching):
    c=coaching
    assign(c)
    from app.models.entities import EvaluationIssue
    with c["factory"]() as db:
        for feature in ("a","a","b","c","d","e","f","g"):
            db.add(EvaluationIssue(evaluation_id=c["eid"],body_part="knee",feature=feature,
                deviation=1,severity="low",feedback="Dataset difference"))
        db.commit()
    result=client.get("/api/v1/coach/overview",headers=c["coach"])
    assert result.status_code == 200,result.text
    assert result.json()["topIssues"] == [{"feature":feature,"sessionCount":1} for feature in "abcdef"]


def test_member_unique_constraint_and_role_validation(client, member, coaching):
    c=coaching
    from sqlalchemy.exc import IntegrityError
    from app.core.errors import DomainError
    with c["factory"]() as db:
        with pytest.raises(DomainError):
            assign_coach(db,c["owner"],c["owner"],"admin","Invalid Coach role")
    assign(c)
    with c["factory"]() as db:
        event=AssignmentEvent(member_id=c["owner"],from_coach_id=c["first"],to_coach_id=c["second"],actor="test",reason="Constraint test")
        db.add(event)
        db.flush()
        with pytest.raises(IntegrityError):
            db.execute(CoachAssignment.__table__.insert().values(member_id=c["owner"],coach_id=c["second"],event_id=event.id,assigned_at=now()))
        db.rollback()
