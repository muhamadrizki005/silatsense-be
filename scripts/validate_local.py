"""Local acceptance check with real MediaPipe inference; run against a disposable database.

The video is a repeated dataset image to validate plumbing, NOT model accuracy.
"""

import json
import secrets
from pathlib import Path
import cv2
import httpx
from PIL import Image, ImageOps
import numpy as np
from app.db.session import SessionLocal
from app.models.entities import User
from app.core.security import passwords


def main():
    cache = Path(".cache")
    cache.mkdir(exist_ok=True)
    source = next(Path("datasets/kuda_kuda/train").glob("*.jpg"))
    with Image.open(source) as image:
        image = ImageOps.exif_transpose(image).convert("RGB").rotate(270, expand=True)
        image.thumbnail((640, 640))
        w, h = image.size
        image = image.resize((w // 2 * 2, h // 2 * 2))
        frame = cv2.cvtColor(np.asarray(image), cv2.COLOR_RGB2BGR)
    video_path = cache / "acceptance-video.mp4"
    writer = cv2.VideoWriter(
        str(video_path),
        cv2.VideoWriter_fourcc(*"mp4v"),
        10,
        (frame.shape[1], frame.shape[0]),
    )
    assert writer.isOpened()
    for _ in range(20):
        writer.write(frame)
    writer.release()
    suffix = secrets.token_hex(4)
    password = secrets.token_urlsafe(16)
    coach_email = f"coach-{suffix}@example.com"
    with SessionLocal() as db:
        db.add(
            User(
                name="Pelatih Validasi",
                email=coach_email,
                role="COACH",
                password_hash=passwords.hash(password),
            )
        )
        db.commit()
    with httpx.Client(base_url="http://localhost:8000/api/v1", timeout=120) as client:
        member_email = f"member-{suffix}@example.com"
        response = client.post(
            "/auth/register",
            json={
                "name": "Pesilat Validasi",
                "email": member_email,
                "password": password,
            },
        )
        response.raise_for_status()
        data = response.json()
        headers = {"Authorization": "Bearer " + data["access_token"]}
        assert len(client.get("/movements").json()) == 4
        checks = []
        for movement in ["kuda_kuda", "pukulan", "tangkisan", "tendangan"]:
            with video_path.open("rb") as video:
                response = client.post(
                    "/evaluations",
                    headers=headers,
                    data={"movement_type": movement},
                    files={"video": ("acceptance.mp4", video, "video/mp4")},
                )
            response.raise_for_status()
            result = response.json()
            assert result["pose_status"] == "detected"
            assert result["analysis"]["frames_processed"] > 0
            if movement in ["pukulan", "tendangan"]:
                assert (
                    result["score"] is None
                    and result["status"] == "reference_not_ready"
                )
            else:
                assert (
                    result["score"] is not None and result["status"] == "experimental"
                )
            checks.append(
                {
                    "movement": movement,
                    "status": result["status"],
                    "frames": result["analysis"]["frames_processed"],
                }
            )
        history = client.get("/evaluations", headers=headers).json()
        assert len(history) == 4
        coach = client.post(
            "/auth/login", json={"email": coach_email, "password": password}
        ).json()
        coach_headers = {"Authorization": "Bearer " + coach["access_token"]}
        evaluation_id = history[-1]["id"]
        note = client.post(
            f"/coach/evaluations/{evaluation_id}/notes",
            headers=coach_headers,
            json={
                "note": "Catatan uji integrasi. Diskusikan posisi tubuh dengan pelatih."
            },
        )
        note.raise_for_status()
        assert client.get(f"/evaluations/{evaluation_id}", headers=headers).json()[
            "coach_notes"
        ]
        (cache / "qa.json").write_text(
            json.dumps(
                {
                    "member_email": member_email,
                    "coach_email": coach_email,
                    "password": password,
                    "evaluation_id": evaluation_id,
                    "member_id": data["user"]["id"],
                }
            ),
            encoding="utf-8",
        )
        print(
            json.dumps(
                {
                    "real_inference": checks,
                    "history_and_coach_note": "passed",
                    "fixture": "Repeated reference image; not accuracy evidence",
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
