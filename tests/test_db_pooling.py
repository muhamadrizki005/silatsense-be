"""Pool budget tests use only disconnected MySQL engines or disposable SQLite."""

import json
import os
import subprocess
import sys

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, event, text
from sqlalchemy.exc import TimeoutError
from sqlalchemy.pool import NullPool, QueuePool, SingletonThreadPool

from app.core.config import Settings
from app.db.session import create_database_engine, engine_options


def config(**overrides):
    return Settings(
        _env_file=None,
        database_url="mysql+pymysql://fixture:private@invalid/test",
        **overrides,
    )


def test_network_pool_defaults_and_overrides_do_not_connect():
    engine = create_database_engine(config())
    try:
        assert isinstance(engine.pool, QueuePool)
        assert engine.pool.size() == 1
        assert engine.pool._max_overflow == 0
        assert engine.pool.timeout() == 5
        assert engine.hide_parameters
        assert engine.pool.checkedin() == 0  # Lazy, no login to any server.
        opts = engine_options(
            config(db_pool_size=2, db_max_overflow=1, db_pool_timeout_seconds=3)
        )
        assert (opts["pool_size"], opts["max_overflow"], opts["pool_timeout"]) == (
            2,
            1,
            3,
        )
        assert opts["connect_args"] == {
            "connect_timeout": 5,
            "read_timeout": 10,
            "write_timeout": 10,
        }
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    "overrides",
    [
        {"db_pool_size": 0},
        {"db_max_overflow": -1},
        {"db_pool_timeout_seconds": 0},
        {"db_pool_mode": "unlimited"},
        {"db_connect_timeout_seconds": 0},
        {"worker_error_backoff_seconds": 20, "worker_error_max_backoff_seconds": 10},
    ],
)
def test_invalid_unbounded_or_inconsistent_settings_are_rejected(overrides):
    with pytest.raises(ValidationError):
        config(**overrides)


def test_pool_settings_load_from_environment(monkeypatch):
    monkeypatch.setenv("DB_POOL_SIZE", "2")
    monkeypatch.setenv("DB_MAX_OVERFLOW", "0")
    assert config().db_pool_size == 2


@pytest.mark.parametrize("mode", ["queue", "null"])
def test_sqlite_keeps_compatible_pool_and_connection_arguments(mode):
    cfg = Settings(_env_file=None, database_url="sqlite://", db_pool_mode=mode)
    opts = engine_options(cfg)
    assert opts == {
        "pool_pre_ping": True,
        "hide_parameters": True,
        "connect_args": {"check_same_thread": False},
    }
    engine = create_database_engine(cfg)
    try:
        assert isinstance(engine.pool, SingletonThreadPool)
        with engine.connect() as db:
            assert db.execute(text("SELECT 1")).scalar() == 1
    finally:
        engine.dispose()


def test_one_slot_rejects_second_checkout_then_reuses_connection(tmp_path):
    opts = engine_options(config(db_pool_timeout_seconds=0.05))
    opts["connect_args"] = {"check_same_thread": False}
    engine = create_engine("sqlite:///" + (tmp_path / "budget.db").as_posix(), **opts)
    opened = []
    event.listen(engine, "connect", lambda *_: opened.append(1))
    try:
        with engine.begin() as db:
            db.execute(text("CREATE TABLE fixture (id INTEGER)"))
        with engine.connect() as first:
            first.execute(text("INSERT INTO fixture VALUES (1)"))
            with pytest.raises(TimeoutError):
                engine.connect()
        with engine.connect() as next_connection:
            assert (
                next_connection.execute(text("SELECT count(*) FROM fixture")).scalar()
                == 0
            )
        assert len(opened) == 1
        assert engine.pool.checkedout() == 0
    finally:
        engine.dispose()


def test_null_pool_does_not_retain_idle_connections(tmp_path):
    opts = engine_options(config(db_pool_mode="null"))
    assert opts["poolclass"] is NullPool
    assert "max_overflow" not in opts and "pool_size" not in opts
    opts["connect_args"] = {}
    engine = create_engine("sqlite:///" + (tmp_path / "null.db").as_posix(), **opts)
    closed = []
    event.listen(engine, "close", lambda *_: closed.append(1))
    try:
        with engine.connect() as first, engine.connect() as second:
            assert first.execute(text("SELECT 1")).scalar() == 1
            assert second.execute(text("SELECT 1")).scalar() == 1
        assert len(closed) == 2  # NullPool is deliberately NOT a concurrency limit.
    finally:
        engine.dispose()


def test_read_only_db_status_uses_selected_disposable_database(tmp_path):
    database = tmp_path / "status.db"
    path = tmp_path / "status.env"
    path.write_text("DATABASE_URL=sqlite:///" + database.as_posix() + "\n")
    result = subprocess.run(
        [sys.executable, "-m", "scripts.db_status", "--env-file", str(path)],
        capture_output=True,
        text=True,
        timeout=20,
        env={**os.environ, "DATABASE_URL": "invalid-url-must-not-be-printed"},
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["status"] == "ok"
    engine = create_engine("sqlite:///" + database.as_posix())
    try:
        with engine.connect() as db:
            assert (
                db.execute(
                    text("SELECT count(*) FROM sqlite_master WHERE type='table'")
                ).scalar()
                == 0
            )
    finally:
        engine.dispose()
