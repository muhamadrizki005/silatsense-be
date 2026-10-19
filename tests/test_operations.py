import json
import logging
from contextlib import contextmanager
from sqlalchemy import text

from app.main import app
from app.db.session import get_db
from app.core.config import settings


def test_readiness_requires_migration_and_writable_storage(
    client, tmp_path, monkeypatch
):
    monkeypatch.setattr(settings, "media_root", str(tmp_path / "private-media"))
    assert client.get("/health/live").status_code == 200
    assert client.get("/health/ready").status_code == 503
    with contextmanager(app.dependency_overrides[get_db])() as db:
        db.execute(
            text("CREATE TABLE alembic_version (version_num VARCHAR(32) PRIMARY KEY)")
        )
        db.execute(text("INSERT INTO alembic_version VALUES ('0007')"))
        db.commit()
    try:
        assert client.get("/health/ready").json()["status"] == "ready"
        blocked = tmp_path / "file"
        blocked.write_text("not a directory")
        monkeypatch.setattr(settings, "media_root", str(blocked))
        assert client.get("/health/ready").status_code == 503
    finally:
        with contextmanager(app.dependency_overrides[get_db])() as db:
            db.execute(text("DROP TABLE alembic_version"))
            db.commit()


def test_http_logs_are_structured_without_credentials_or_query(client, caplog):
    with caplog.at_level(logging.INFO, logger="silatsense.http"):
        response = client.post(
            "/api/v1/auth/sign-in?token=must-not-log",
            json={"identifier": "unknown@example.com", "password": "password123"},
        )
    record = next(
        json.loads(row.message)
        for row in caplog.records
        if row.name == "silatsense.http"
    )
    assert record["requestId"] == response.headers["x-request-id"]
    assert record["route"] == "/api/v1/auth/sign-in" and record["status"] == 401
    assert (
        "must-not-log" not in caplog.text
        and "password123" not in caplog.text
        and "unknown@example.com" not in caplog.text
    )
    assert response.headers["cache-control"] == "no-store"
