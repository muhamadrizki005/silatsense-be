"""No real jobs or network: exercise safe diagnostics and interruptible retries."""

import json
import logging

import pymysql
import pytest
from sqlalchemy.exc import ArgumentError, OperationalError, TimeoutError

from app.core.config import settings
from app.core.error_metadata import safe_error_metadata
from app.services.worker import Worker


SECRET = "mysql+pymysql://private:password@host/db?X-Amz-Signature=secret"


def capacity_error():
    return OperationalError(
        "SELECT private_statement",
        {"private_parameter": SECRET},
        pymysql.err.OperationalError(
            1226,
            "User 'private_user' has exceeded the 'max_user_connections' resource (current value: 5) "
            + SECRET,
        ),
    )


def test_capacity_diagnostic_is_strictly_allowlisted():
    assert safe_error_metadata(capacity_error()) == {
        "errorCategory": "database_capacity",
        "dbErrorCode": 1226,
        "resource": "max_user_connections",
        "resourceLimit": 5,
    }


@pytest.mark.parametrize(
    "code, category",
    [
        (1040, "database_capacity"),
        (1045, "database_authentication"),
        (2003, "database_connection"),
        (2013, "database_connection"),
        (999, "database_error"),
    ],
)
def test_db_error_categories_never_include_message(code, category):
    assert safe_error_metadata(pymysql.err.OperationalError(code, SECRET)) == {
        "errorCategory": category,
        "dbErrorCode": code,
    }


@pytest.mark.parametrize(
    "error, category",
    [
        (TimeoutError(SECRET), "database_pool_timeout"),
        (ArgumentError(SECRET), "database_configuration"),
        (RuntimeError(SECRET), "unexpected_error"),
        (OSError(SECRET), "filesystem_error"),
    ],
)
def test_non_dbapi_messages_are_not_logged(error, category):
    assert safe_error_metadata(error) == {"errorCategory": category}


class FakeStop:
    def __init__(self, limit):
        self.delays = []
        self.limit = limit

    def is_set(self):
        return len(self.delays) >= self.limit

    def wait(self, seconds):
        self.delays.append(seconds)
        return self.is_set()


def test_worker_capacity_backoff_caps_resets_and_redacts(caplog, monkeypatch):
    monkeypatch.setattr(settings, "worker_error_backoff_seconds", 5)
    monkeypatch.setattr(settings, "worker_error_max_backoff_seconds", 12)
    monkeypatch.setattr(settings, "worker_poll_seconds", 1)
    stop = FakeStop(6)
    worker = Worker(None, "test-worker", stop)
    outcomes = iter(
        [
            capacity_error(),
            capacity_error(),
            capacity_error(),
            capacity_error(),
            False,
            capacity_error(),
        ]
    )

    def iteration():
        value = next(outcomes)
        if isinstance(value, Exception):
            raise value
        return value

    monkeypatch.setattr(worker, "run_once", iteration)
    with caplog.at_level(logging.ERROR, logger="app.services.worker"):
        worker.run_forever()
    assert stop.delays == [5, 10, 12, 12, 1, 5]
    assert len(caplog.records) == 5
    for record in caplog.records:
        body = json.loads(record.message)
        assert body["dbErrorCode"] == 1226
        assert body["resourceLimit"] == 5
        assert record.exc_info is None
    for private in (SECRET, "private_user", "private_statement", "private_parameter"):
        assert private not in caplog.text


def test_worker_shutdown_does_not_run_iteration():
    worker = Worker(None, "test-worker", FakeStop(0))
    worker.run_once = lambda: pytest.fail("Stopped worker must not touch the queue")
    worker.run_forever()
