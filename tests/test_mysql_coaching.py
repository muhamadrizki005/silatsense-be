from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import os

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import func, select

from app.main import app
from app.models.entities import AssignmentEvent, CoachAssignment, FollowUpTask, ReviewRevision
from app.services.assignments import assign_coach
from test_coaching import coaching, assign, draft

pytestmark = pytest.mark.skipif(not os.environ.get("TEST_DATABASE_URL", "").startswith("mysql"),
    reason="Assignment/review races require native disposable MySQL row locks")


def test_simultaneous_assignment_keeps_one_current_and_ordered_history(client, member, coaching):
    c=coaching
    barrier=Barrier(2)
    def work(coach_id):
        with c["factory"]() as db:
            barrier.wait(timeout=10)
            return assign_coach(db,c["owner"],coach_id,"native-test-admin","Race assignment")
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(work,[c["first"],c["second"]]))
    with c["factory"]() as db:
        assert db.scalar(select(func.count()).select_from(CoachAssignment)) == 1
        events=db.scalars(select(AssignmentEvent).order_by(AssignmentEvent.id)).all()
        assert len(events) == 2 and events[0].from_coach_id is None
        assert events[1].from_coach_id == events[0].to_coach_id
        assert db.get(CoachAssignment,c["owner"]).coach_id == events[1].to_coach_id


@pytest.mark.parametrize("same_key",[True,False])
def test_parallel_publish_has_one_revision_and_one_task(client, member, coaching, same_key):
    c=coaching
    assign(c)
    assert draft(client,c).status_code == 200
    barrier=Barrier(2)
    def work(index):
        with TestClient(app) as other:
            barrier.wait(timeout=10)
            return other.post(f"/api/v1/coach/sessions/{c['sid']}/reviews",
                headers={**c["coach"],"Idempotency-Key":"same" if same_key else f"key-{index}"},
                json={"expectedRevision":0,"expectedDraftVersion":1})
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses=list(pool.map(work,range(2)))
    assert sorted(r.status_code for r in responses) == ([201,201] if same_key else [201,409])
    with c["factory"]() as db:
        assert db.scalar(select(func.count()).select_from(ReviewRevision)) == 1
        assert db.scalar(select(func.count()).select_from(FollowUpTask)) == 1


def test_transfer_racing_publish_has_a_serial_authorization_order(client, member, coaching):
    c=coaching
    assign(c)
    draft(client,c)
    barrier=Barrier(2)
    def transfer():
        with c["factory"]() as db:
            barrier.wait(timeout=10)
            return assign_coach(db,c["owner"],c["second"],"native-test-admin","Transfer race")
    def publish():
        with TestClient(app) as other:
            barrier.wait(timeout=10)
            return other.post(f"/api/v1/coach/sessions/{c['sid']}/reviews",
                headers={**c["coach"],"Idempotency-Key":"publish-transfer"},
                json={"expectedRevision":0,"expectedDraftVersion":1})
    with ThreadPoolExecutor(max_workers=2) as pool:
        a,b=pool.submit(transfer),pool.submit(publish)
        a.result(timeout=20)
        result=b.result(timeout=20)
    assert result.status_code in (201,404),result.text
    with c["factory"]() as db:
        assert db.get(CoachAssignment,c["owner"]).coach_id == c["second"]
        assert db.scalar(select(func.count()).select_from(ReviewRevision)) == int(result.status_code == 201)
    assert client.get(f"/api/v1/coach/sessions/{c['sid']}",headers=c["coach"]).status_code == 404
