from contextlib import contextmanager
from datetime import timedelta, timezone
import hashlib
from io import BytesIO
from pathlib import Path

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.db.session import get_db
from app.main import app
from app.models.entities import (
    AnalysisJob,
    DirectUpload,
    MediaAsset,
    UploadReservation,
    now,
)
from app.services import storage as storage_module
from app.services.cleanup import cleanup_once
from app.services.storage import B2Storage, StorageUnavailable
from app.services.worker import Worker


class FakeS3:
    """Versioned object service: exercise the real adapter without cloud credentials."""

    def __init__(self):
        self.objects, self.counter, self.signed = {}, 0, []
        self.down = False

    def put_object(self, Bucket, Key, Body, ContentType="application/octet-stream"):
        self.counter += 1
        item = {
            "VersionId": str(self.counter),
            "data": Body,
            "ContentType": ContentType,
            "LastModified": now().replace(tzinfo=timezone.utc),
        }
        self.objects.setdefault(Key, []).append(item)
        return {"VersionId": item["VersionId"]}

    def head_object(self, Bucket, Key):
        if self.down:
            raise RuntimeError("secret must never escape")
        if not self.objects.get(Key):
            raise FileNotFoundError()
        item = self.objects[Key][-1]
        return {**item, "ContentLength": len(item["data"])}

    def generate_presigned_url(self, operation, **kwargs):
        self.signed.append(kwargs)
        return "https://storage.invalid/signed-put?secret=do-not-log"

    def copy_object(self, Bucket, Key, CopySource):
        source = next(
            v
            for v in self.objects[CopySource["Key"]]
            if v["VersionId"] == CopySource["VersionId"]
        )
        return self.put_object(Bucket, Key, source["data"], source["ContentType"])

    def get_object(self, Bucket, Key, Range=None):
        item = self.head_object(Bucket, Key)
        data = item["data"]
        if Range:
            start, end = map(int, Range.removeprefix("bytes=").split("-"))
            data = data[start : end + 1]
        return {"Body": BytesIO(data), "ContentLength": len(data)}

    def list_object_versions(self, Bucket, Prefix, MaxKeys):
        return {
            "Versions": [
                {"Key": key, **{k: v for k, v in item.items() if k != "data"}}
                for key, values in self.objects.items()
                if key.startswith(Prefix)
                for item in values
            ]
        }

    def delete_object(self, Bucket, Key, VersionId):
        self.objects[Key] = [
            item for item in self.objects[Key] if item["VersionId"] != VersionId
        ]
        return {}


@pytest.fixture
def remote(client, member, monkeypatch):
    monkeypatch.setattr(settings, "storage_adapter", "b2")
    monkeypatch.setattr(settings, "b2_bucket", "test-private")
    monkeypatch.setattr(settings, "pose_model_sha256", "a" * 64)
    fake = FakeS3()
    adapter = B2Storage(client=fake)
    monkeypatch.setattr(storage_module, "B2Storage", lambda: adapter)
    factory = contextmanager(app.dependency_overrides[get_db])
    return fake, adapter, factory


def request_body(data=b"not-yet-validated"):
    return {
        "movementSlug": "pukulan",
        "filename": "video.mp4",
        "mimeType": "video/mp4",
        "byteSize": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def initiate(client, member, body=None, key="one"):
    return client.post(
        "/api/v1/member/uploads",
        headers={**member, "Idempotency-Key": key},
        json=body or request_body(),
    )


def put(fake, ticket, data=b"not-yet-validated", mime="video/mp4"):
    fake.put_object("test-private", f"staging/{ticket['uploadId']}.part", data, mime)


def finish(client, member, ticket):
    return client.post(ticket["completePath"], headers=member)


def test_upload_control_flow_replay_and_pinned_media(client, member, remote):
    fake, adapter, factory = remote
    response = initiate(client, member)
    assert response.status_code == 201, response.text
    ticket = response.json()
    signed = fake.signed[-1]
    assert signed["Params"]["ContentLength"] == request_body()["byteSize"]
    assert signed["Params"]["ContentType"] == "video/mp4"
    assert 0 < signed["ExpiresIn"] <= settings.upload_reservation_seconds
    assert initiate(client, member).json()["uploadId"] == ticket["uploadId"]
    put(fake, ticket)
    complete = finish(client, member, ticket)
    assert complete.status_code == 202, complete.text
    assert finish(client, member, ticket).json() == complete.json()
    replay = initiate(client, member).json()
    assert replay["uploadUrl"] is None and replay["acceptedSession"] == complete.json()
    with factory() as db:
        assert len(db.scalars(select(AnalysisJob)).all()) == 1
        assert db.scalar(select(UploadReservation)) is None
        media = db.scalar(select(MediaAsset))
        key = media.storage_key
        assert media.duration_seconds is media.width is media.height is None
        from app.models.entities import TrainingSession

        assert media.expires_at - db.get(
            TrainingSession, media.session_id
        ).uploaded_at == timedelta(hours=24)
    original = adapter.head(key)["data"]
    put(fake, ticket, data=b"overwritten after complete")
    assert adapter.head(key)["data"] == original
    status = client.get(complete.json()["statusUrl"], headers=member).json()
    assert status["media"]["status"] == "unavailable"
    assert status["media"]["width"] is None
    assert (
        client.get(complete.json()["statusUrl"] + "/video", headers=member).status_code
        == 409
    )


@pytest.mark.parametrize(
    "field,value,status",
    [
        ("byteSize", 101 * 1024 * 1024, 413),
        ("byteSize", 0, 422),
        ("sha256", "wrong", 422),
        ("filename", "video.exe", 415),
        ("movementSlug", "kuda_kuda", 422),
        ("mimeType", "text/html", 422),
    ],
)
def test_rejects_invalid_upload_request(client, member, remote, field, value, status):
    body = request_body()
    body[field] = value
    assert initiate(client, member, body).status_code == status


def test_quota_idempotency_expiry_and_ownership(client, member, remote, monkeypatch):
    fake, _, factory = remote
    monkeypatch.setattr(settings, "max_pending_sessions", 1)
    ticket = initiate(client, member).json()
    assert initiate(client, member).status_code == 201
    assert initiate(client, member, request_body(b"other")).status_code == 409
    assert initiate(client, member, key="second").status_code == 429
    assert finish(client, {}, ticket).status_code == 401
    other = client.post(
        "/api/v1/auth/sign-up",
        json={
            "fullName": "Other",
            "identifier": "other@example.com",
            "password": "password123",
        },
    ).json()
    assert (
        finish(
            client, {"Authorization": "Bearer " + other["accessToken"]}, ticket
        ).status_code
        == 404
    )
    with factory() as db:
        db.get(DirectUpload, ticket["uploadId"]).expires_at = now() - timedelta(
            seconds=1
        )
        db.get(UploadReservation, ticket["uploadId"]).expires_at = now() - timedelta(
            seconds=1
        )
        db.commit()
    assert finish(client, member, ticket).status_code == 410
    assert initiate(client, member).status_code == 410
    cleanup_once(factory)
    assert initiate(client, member, key="second").status_code == 201


def test_wrong_size_type_and_outage_do_not_enqueue(client, member, remote):
    fake, _, factory = remote
    ticket = initiate(client, member).json()
    assert finish(client, member, ticket).json()["code"] == "upload_incomplete"
    put(fake, ticket, b"wrong")
    assert finish(client, member, ticket).status_code == 422
    put(fake, ticket, mime="text/html")
    assert finish(client, member, ticket).status_code == 422
    fake.down = True
    response = finish(client, member, ticket)
    assert response.status_code == 503 and "secret" not in response.text
    with factory() as db:
        assert db.scalar(select(AnalysisJob)) is None


def test_large_playback_is_bounded_and_stops_at_exact_expiry(
    client, member, remote, monkeypatch
):
    fake, _, factory = remote
    data = b"x" * (5 * 1024 * 1024)
    ticket = initiate(client, member, request_body(data)).json()
    put(fake, ticket, data)
    accepted = finish(client, member, ticket).json()
    with factory() as db:
        media = db.scalar(select(MediaAsset))
        media.width, media.height, media.duration_seconds = 64, 64, 1
        expiry = media.expires_at
        db.commit()
    url = accepted["statusUrl"] + "/video"
    assert client.get(url, headers=member).json()["code"] == "media_range_required"
    response = client.get(url, headers={**member, "Range": "bytes=0-"})
    assert response.status_code == 206 and len(response.content) == 4 * 1024 * 1024
    assert response.headers["content-range"] == f"bytes 0-4194303/{len(data)}"
    tail = client.get(url, headers={**member, "Range": "bytes=4194304-"})
    assert len(tail.content) == 1024 * 1024
    monkeypatch.setattr("app.services.media.now", lambda: expiry)
    assert client.get(url, headers={**member, "Range": "bytes=0-1"}).status_code == 410


def test_b2_readiness_checks_real_operations_with_fake_service(client, remote):
    from sqlalchemy import text

    fake, _, factory = remote
    with factory() as db:
        db.execute(
            text("CREATE TABLE alembic_version (version_num VARCHAR(32) PRIMARY KEY)")
        )
        db.execute(text("INSERT INTO alembic_version VALUES ('0008')"))
        db.commit()
    try:
        response = client.get("/health/ready")
        assert response.status_code == 200, response.text
        assert response.json()["components"]["storage"] == "ok"
        assert all(not versions for versions in fake.objects.values())
        fake.down = True
        assert client.get("/health/ready").status_code == 503
    finally:
        with factory() as db:
            db.execute(text("DROP TABLE alembic_version"))
            db.commit()


def test_worker_download_checksum_validation_and_playback(
    client, member, remote, tmp_path, monkeypatch
):
    import cv2
    import numpy as np

    fake, _, factory = remote
    path = tmp_path / "video.mp4"
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 10, (64, 64))
    for _ in range(10):
        writer.write(np.zeros((64, 64, 3), dtype=np.uint8))
    writer.release()
    data = path.read_bytes()
    ticket = initiate(client, member, request_body(data)).json()
    put(fake, ticket, data)
    accepted = finish(client, member, ticket).json()
    # Exercise real download/probe; inference is independent of storage.
    observed = []
    monkeypatch.setattr(
        Worker,
        "_analyze",
        lambda self, claim, path: observed.append(Path(path).read_bytes()),
    )
    assert Worker(factory, "test-worker").run_once()
    assert observed == [data]
    with factory() as db:
        media = db.scalar(select(MediaAsset))
        assert media.width == 64 and media.duration_seconds == 1
        key = media.storage_key
    url = accepted["statusUrl"] + "/video"
    response = client.get(url, headers={**member, "Range": "bytes=2-15"})
    assert response.status_code == 206 and response.content == data[2:16]
    assert (
        client.get(url, headers={**member, "Range": "bytes=99999999-"}).status_code
        == 416
    )
    with factory() as db:
        db.scalar(select(MediaAsset)).expires_at = now() - timedelta(seconds=1)
        db.commit()
    assert client.get(url, headers=member).status_code == 410
    # Active worker lease fences deletion; after its expiry cleanup purges versions.
    with factory() as db:
        db.scalar(select(AnalysisJob)).lease_until = now() - timedelta(seconds=1)
        db.commit()
    cleanup_once(factory)
    assert not fake.objects[key]
    assert cleanup_once(factory) == 0


def test_bad_checksum_and_invalid_video_fail_before_inference(
    client, member, remote, monkeypatch
):
    fake, _, factory = remote
    body = request_body()
    body["sha256"] = "b" * 64
    ticket = initiate(client, member, body).json()
    put(fake, ticket)
    assert finish(client, member, ticket).status_code == 202
    monkeypatch.setattr(
        Worker,
        "_analyze",
        lambda *args: pytest.fail("unvalidated video reached inference"),
    )
    Worker(factory, "test-worker").run_once()
    with factory() as db:
        assert db.scalar(select(AnalysisJob)).state == "failed"
        assert db.scalar(select(MediaAsset)).width is None
    second = initiate(client, member, key="second").json()
    put(fake, second)
    finish(client, member, second)
    Worker(factory, "test-worker").run_once()
    with factory() as db:
        jobs = db.scalars(select(AnalysisJob).order_by(AnalysisJob.id)).all()
        assert jobs[-1].last_error_code == "invalid_video"


def test_local_mode_unchanged_and_missing_worker_configuration(
    client, member, monkeypatch
):
    assert initiate(client, member).status_code == 503
    monkeypatch.setattr(settings, "storage_adapter", "b2")
    monkeypatch.setattr(settings, "pose_model_sha256", None)
    response = initiate(client, member)
    assert response.json()["code"] == "worker_configuration_required"


def test_adapter_range_download_cleanup_and_failure_redaction(remote):
    fake, adapter, _ = remote
    key = "objects/" + "a" * 32 + ".mp4"
    fake.put_object("test-private", key, b"one")
    fake.put_object("test-private", key, b"two")
    with adapter.materialize(key, checksum=hashlib.sha256(b"two").hexdigest()) as path:
        downloaded = path
        assert path.read_bytes() == b"two"
    assert not downloaded.exists()
    with pytest.raises(ValueError):
        with adapter.materialize(key, checksum="a" * 64):
            pass
    adapter.delete(key)
    adapter.delete(key)
    assert fake.objects[key] == []
    fake.down = True
    with pytest.raises(StorageUnavailable, match="Object storage operation failed"):
        adapter.head(key)


def test_real_boto_signing_binds_size_type_and_staging(monkeypatch):
    from urllib.parse import parse_qs, urlsplit

    monkeypatch.setattr(settings, "b2_bucket", "private-test")
    monkeypatch.setattr(settings, "b2_key_id", "test-only-key")
    monkeypatch.setattr(settings, "b2_application_key", "test-only-secret")
    url = B2Storage().presign("staging/" + "a" * 32 + ".part", 123, "video/mp4", 60)
    params = parse_qs(urlsplit(url).query)
    assert params["X-Amz-SignedHeaders"] == ["content-length;content-type;host"]
    assert params["X-Amz-Expires"] == ["60"]
