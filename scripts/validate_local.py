"""Manual HTTP acceptance check against an explicitly configured disposable DB.

Start API and worker using that same *_test database first. Supply an owned video;
this checks application plumbing and never claims scientific model accuracy.
"""

import argparse
from pathlib import Path
import secrets
import time
from uuid import uuid4

import httpx
from app.core.security import passwords
from app.db.session import SessionLocal, engine
from app.models.entities import User
from app.services.assignments import assign_coach


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--base-url", default="http://localhost:8001/api/v1")
    parser.add_argument("--timeout", type=int, default=240)
    args = parser.parse_args()
    if not (engine.url.database or "").endswith("_test"):
        parser.error(
            "Only a disposable *_test database is allowed; never use development."
        )
    if not args.video.is_file() or args.timeout < 1:
        parser.error("Supply an existing video and a positive timeout.")
    suffix, password = secrets.token_hex(8), secrets.token_urlsafe(24)
    member_email = f"member-{suffix}@example.com"
    coach_email = f"coach-{suffix}@example.com"
    with httpx.Client(base_url=args.base_url.rstrip("/") + "/", timeout=60) as client:
        created = client.post(
            "auth/sign-up",
            json={
                "fullName": "Member Validasi",
                "identifier": member_email,
                "password": password,
            },
        )
        created.raise_for_status()
        auth = created.json()
        owner_id = int(auth["user"]["id"])
        member_headers = {"Authorization": "Bearer " + auth["accessToken"]}
        with SessionLocal() as db:
            owner = db.get(User, owner_id)
            if not owner or owner.email != member_email:
                raise RuntimeError(
                    "API must use the same disposable database as this CLI."
                )
            coach = User(
                name="Coach Validasi",
                email=coach_email,
                role="COACH",
                password_hash=passwords.hash(password),
            )
            db.add(coach)
            db.commit()
            coach_id = coach.id
            assign_coach(
                db, owner_id, coach_id, "validate-local", "Disposable acceptance run"
            )
        catalog = client.get("member/training-modules", headers=member_headers)
        catalog.raise_for_status()
        assert len(catalog.json()["modules"]) == 4
        with args.video.open("rb") as video:
            accepted = client.post(
                "member/sessions",
                headers={
                    **member_headers,
                    "Idempotency-Key": str(uuid4()),
                },
                data={"movementSlug": "kuda-kuda"},
                files={"video": (args.video.name, video, "application/octet-stream")},
            )
        accepted.raise_for_status()
        sid = accepted.json()["sessionId"]
        deadline = time.monotonic() + args.timeout
        while True:
            response = client.get(f"member/sessions/{sid}", headers=member_headers)
            response.raise_for_status()
            status = response.json()
            if status["processingStatus"] == "completed":
                break
            if status["processingStatus"] == "failed":
                raise RuntimeError(
                    "Video processing failed: " + status["error"]["code"]
                )
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    "Worker did not finish within the acceptance timeout."
                )
            time.sleep(2)
        evaluation = client.get(
            f"member/sessions/{sid}/evaluation", headers=member_headers
        )
        evaluation.raise_for_status()
        assert evaluation.json()["sessionId"] == sid
        history = client.get("member/history", headers=member_headers)
        history.raise_for_status()
        assert history.json()["items"][0]["session"]["id"] == sid
        login = client.post(
            "auth/sign-in", json={"identifier": coach_email, "password": password}
        )
        login.raise_for_status()
        coach_headers = {"Authorization": "Bearer " + login.json()["accessToken"]}
        draft = client.put(
            f"coach/sessions/{sid}/feedback-draft",
            headers=coach_headers,
            json={
                "expectedVersion": 0,
                "decision": "approved",
                "note": "Uji alur aplikasi.",
            },
        )
        draft.raise_for_status()
        review = client.post(
            f"coach/sessions/{sid}/reviews",
            headers={
                **coach_headers,
                "Idempotency-Key": str(uuid4()),
            },
            json={
                "expectedRevision": 0,
                "expectedDraftVersion": draft.json()["version"],
            },
        )
        review.raise_for_status()
        detail = client.get(f"member/history/{sid}", headers=member_headers)
        detail.raise_for_status()
        assert detail.json()["review"]["id"] == review.json()["id"]
    print(
        "PASS: sign-up, catalog, queued upload/worker, evaluation, history and Coach review."
    )
    print(
        "Disposable fixtures remain in the *_test schema; no credentials were written to disk."
    )


if __name__ == "__main__":
    main()
