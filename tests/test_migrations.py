from datetime import datetime, timedelta
import os

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import MetaData, create_engine, inspect, select
from sqlalchemy.engine import make_url

from app.core.config import settings


@pytest.fixture
def migration_url(tmp_path):
    url = os.environ.get("MIGRATION_TEST_DATABASE_URL")
    if not url:
        yield "sqlite:///" + (tmp_path / "migration.db").as_posix()
        return
    parsed = make_url(url)
    assert parsed.drivername.startswith("mysql") and parsed.database.endswith("_test")
    api_url = os.environ.get("TEST_DATABASE_URL")
    assert not api_url or parsed.database != make_url(api_url).database, "Use a separate migration test schema"
    engine = create_engine(url)
    assert not inspect(engine).get_table_names(), "Migration tests require an empty disposable schema"
    try:
        yield url
    finally:
        metadata = MetaData()
        metadata.reflect(engine)
        metadata.drop_all(engine)
        engine.dispose()


def test_migration_preserves_existing_accounts_tokens_and_history(migration_url, monkeypatch):
    url = migration_url
    monkeypatch.setattr(settings, "database_url", url)
    config = Config("alembic.ini")
    command.upgrade(config, "0002")
    engine = create_engine(url)
    old = MetaData()
    old.reflect(engine)
    timestamp = datetime(2026, 10, 16, 12, 0)
    with engine.begin() as db:
        db.execute(old.tables["users"].insert(), [
            {"id": 1, "name": "Existing Member", "email": None, "npm": "227006104",
             "password_hash": "existing-hash", "role": "MEMBER", "created_at": timestamp},
            {"id": 2, "name": "Existing Coach", "email": "coach@example.com", "npm": None,
             "password_hash": "coach-hash", "role": "COACH", "created_at": timestamp},
        ])
        db.execute(old.tables["refresh_tokens"].insert(), {
            "id": 1, "user_id": 1, "token_hash": "a" * 64,
            "expires_at": timestamp + timedelta(days=7), "persistent": True, "revoked": False,
        })
        db.execute(old.tables["movements"].insert(), {"id": 1, "slug": "kuda_kuda", "name": "Kuda-kuda", "active": True})
        db.execute(old.tables["evaluation_sessions"].insert(), {
            "id": 1, "user_id": 1, "movement": "kuda_kuda", "score": 75,
            "status": "experimental", "analyzer_version": "prototype-v1",
            "reference_version": "old-v1", "result_json": {"score": 75}, "created_at": timestamp,
        })
        db.execute(old.tables["coach_notes"].insert(), {
            "id": 1, "evaluation_id": 1, "coach_id": 2, "note": "Existing review", "created_at": timestamp,
        })
    command.upgrade(config, "head")
    command.check(config)
    metadata = MetaData()
    metadata.reflect(engine)
    assert {"ix_training_owner_history", "ix_training_owner_completed"} <= {
        row["name"] for row in inspect(engine).get_indexes("training_sessions")}
    with engine.connect() as db:
        users = db.execute(select(metadata.tables["users"]).order_by(metadata.tables["users"].c.id)).mappings().all()
        assert users[0]["email"] is None and users[0]["npm"] == "227006104"
        assert users[0]["password_hash"] == "existing-hash" and users[0]["auth_version"] == 0
        assert users[0]["password_changed_at"] is None and users[1]["email_verified_at"] is None
        token = db.execute(select(metadata.tables["refresh_tokens"])).mappings().one()
        assert token["auth_version"] == 0 and not token["revoked"] and token["persistent"]
        assert db.scalar(select(metadata.tables["movements"].c.display_order)) == 1
        assert db.scalar(select(metadata.tables["evaluation_sessions"].c.score)) == 75
        assert db.scalar(select(metadata.tables["coach_notes"].c.coach_id)) == 2
        assert db.scalar(select(metadata.tables["coach_notes"].c.note)) == "Existing review"
        assert db.scalar(select(metadata.tables["evaluation_sessions"].c.training_session_id)) == 1
        session = db.execute(select(metadata.tables["training_sessions"])).mappings().one()
        assert session["processing_status"] == "completed" and session["uploaded_at"] is None
        assert not db.execute(select(metadata.tables["media_assets"])).all()
    command.downgrade(config, "0002")
    command.upgrade(config, "head")
    command.check(config)
    engine.dispose()


def test_migration_empty_database_matches_models(migration_url, monkeypatch):
    monkeypatch.setattr(settings, "database_url", migration_url)
    config = Config("alembic.ini")
    command.upgrade(config, "head")
    command.check(config)


def test_phase5_indexes_preserve_existing_session_data(migration_url, monkeypatch):
    monkeypatch.setattr(settings, "database_url", migration_url)
    config = Config("alembic.ini")
    command.upgrade(config, "0004")
    engine = create_engine(migration_url)
    metadata = MetaData()
    metadata.reflect(engine)
    timestamp = datetime(2026, 10, 18, 12, 30)
    with engine.begin() as db:
        db.execute(metadata.tables["users"].insert(), dict(id=1, name="Member", npm="227006104",
            password_hash="unchanged", role="MEMBER", created_at=timestamp, auth_version=0))
        db.execute(metadata.tables["training_sessions"].insert(), dict(id=8, user_id=1,
            movement="pukulan", processing_status="completed", created_at=timestamp,
            completed_at=timestamp, acknowledged_at=timestamp))
        db.execute(metadata.tables["evaluation_sessions"].insert(), dict(id=15, training_session_id=8,
            user_id=1, movement="pukulan", score=None, status="reference_not_ready",
            analyzer_version="prototype-v1", result_json={"unchanged": True}, created_at=timestamp))
    for action, target in ((command.upgrade, "head"), (command.downgrade, "0004"), (command.upgrade, "head")):
        action(config, target)
        with engine.connect() as db:
            row = db.execute(select(metadata.tables["training_sessions"])).mappings().one()
            assert row["id"] == 8 and row["acknowledged_at"] == timestamp
            assert db.scalar(select(metadata.tables["evaluation_sessions"].c.result_json)) == {"unchanged": True}
            assert db.scalar(select(metadata.tables["users"].c.password_hash)) == "unchanged"
    command.check(config)
    engine.dispose()


def test_phase6_preserves_legacy_notes_and_queue_without_automatic_assignments(migration_url, monkeypatch):
    monkeypatch.setattr(settings,"database_url",migration_url)
    config=Config("alembic.ini")
    command.upgrade(config,"0005")
    engine=create_engine(migration_url)
    metadata=MetaData()
    metadata.reflect(engine)
    timestamp=datetime(2026,10,18,12)
    with engine.begin() as db:
        for uid,role in ((1,"MEMBER"),(2,"COACH")):
            db.execute(metadata.tables["users"].insert(),dict(id=uid,name=role,email=f"{role.lower()}@example.com",password_hash="unchanged",role=role,created_at=timestamp,auth_version=0))
        db.execute(metadata.tables["training_sessions"].insert(),dict(id=9,user_id=1,movement="pukulan",processing_status="queued",created_at=timestamp))
        db.execute(metadata.tables["analysis_jobs"].insert(),dict(id=3,session_id=9,state="queued",attempt=0,available_at=timestamp,reference_snapshot=[],processing_config={"unchanged":True},created_at=timestamp))
        db.execute(metadata.tables["evaluation_sessions"].insert(),dict(id=7,user_id=1,movement="pukulan",score=None,status="reference_not_ready",analyzer_version="prototype-v1",result_json={"unchanged":True},created_at=timestamp))
        db.execute(metadata.tables["coach_notes"].insert(),dict(id=4,evaluation_id=7,coach_id=2,note="Legacy note",created_at=timestamp))
    for action,target in ((command.upgrade,"head"),(command.downgrade,"0005"),(command.upgrade,"head")):
        action(config,target)
        with engine.connect() as db:
            assert db.scalar(select(metadata.tables["coach_notes"].c.note)) == "Legacy note"
            assert db.scalar(select(metadata.tables["analysis_jobs"].c.processing_config)) == {"unchanged":True}
        if target == "head":
            current=MetaData()
            current.reflect(engine)
            with engine.connect() as db:
                assert not db.execute(select(current.tables["coach_member_assignments"])).all()
                assert not db.execute(select(current.tables["review_revisions"])).all()
    command.check(config)
    engine.dispose()
