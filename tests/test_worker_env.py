"""Laptop worker env selection must precede settings imports and never claim jobs on check."""

import json
import os
import subprocess
import sys

from sqlalchemy import create_engine, text

from app.db.session import Base


def run(module, *args):
    return subprocess.run(
        [sys.executable, "-m", module, *map(str, args)],
        capture_output=True,
        text=True,
        timeout=30,
        env={**os.environ, "DATABASE_URL": "must-be-overridden-not-a-real-url"},
    )


def test_worker_and_cleanup_load_selected_env_before_settings(tmp_path):
    path = tmp_path / "worker test.env"
    engine = create_engine("sqlite:///" + (tmp_path / "worker.db").as_posix())
    Base.metadata.create_all(engine)
    with engine.begin() as db:
        db.execute(
            text("CREATE TABLE alembic_version (version_num VARCHAR(32) PRIMARY KEY)")
        )
        db.execute(text("INSERT INTO alembic_version VALUES ('0008')"))
    path.write_text(
        "\n".join(
            [
                "DATABASE_URL=" + str(engine.url),
                "STORAGE_ADAPTER=local",
                "ANALYSIS_MODE=static",
                "MAIL_ADAPTER=disabled",
                "MEDIA_ROOT=" + (tmp_path / "media").as_posix(),
            ]
        )
    )
    checked = run("scripts.worker", "--env-file", path, "--check")
    assert checked.returncode == 0, checked.stderr
    assert json.loads(checked.stdout) == {
        "status": "ready",
        "analysisMode": "static",
        "workerActive": False,
    }
    queued = run("scripts.queue_status", "--env-file", path)
    assert queued.returncode == 0 and json.loads(queued.stdout)["queue"] == {}
    cleanup = run("scripts.cleanup_media", "--env-file", path, "--once")
    assert cleanup.returncode == 0, cleanup.stderr
    engine.dispose()


def test_worker_check_failure_redacts_credentials_and_paths(tmp_path):
    path = tmp_path / "invalid.env"
    path.write_text(
        "ANALYSIS_MODE=coach-reference\nCOACH_REFERENCE_MODEL_PATH=missing-private-model\nDATABASE_URL=mysql+pymysql://user:do-not-print-password@invalid/db\n"
    )
    checked = run("scripts.worker", "--env-file", path, "--check")
    assert checked.returncode == 1
    assert json.loads(checked.stdout) == {
        "status": "not_ready",
        "failedComponent": "model",
        "workerActive": False,
    }
    assert "do-not-print-password" not in checked.stdout + checked.stderr
    assert "missing-private-model" not in checked.stdout + checked.stderr


def test_missing_env_file_is_rejected_before_importing_app_settings(tmp_path):
    result = run("scripts.worker", "--env-file", tmp_path / "missing.env", "--check")
    assert result.returncode == 2 and "Environment file is missing" in result.stderr
    assert "must-be-overridden" not in result.stderr
