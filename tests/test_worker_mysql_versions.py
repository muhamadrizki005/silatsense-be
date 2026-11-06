from datetime import datetime

import pytest
from sqlalchemy.dialects.mysql import dialect as mysql_dialect
from sqlalchemy.dialects.sqlite import dialect as sqlite_dialect

from app.repositories.jobs import claim_statement


@pytest.mark.parametrize(
    "version,mariadb,skip",
    [
        ((5, 7, 44), False, False),
        ((8, 0, 0), False, False),
        ((8, 0, 1), False, True),
        ((8, 4, 0), False, True),
        ((10, 5, 0), True, False),
        ((10, 6, 0), True, True),
        (None, False, False),
    ],
)
def test_claim_sql_is_accepted_by_target_mysql_generation(version, mariadb, skip):
    dialect = mysql_dialect()
    dialect.server_version_info = version
    dialect.is_mariadb = mariadb
    statement = str(
        claim_statement(datetime(2026, 11, 6), dialect).compile(dialect=dialect)
    )
    assert "FOR UPDATE" in statement
    assert ("SKIP LOCKED" in statement) is skip
    assert (
        "LIMIT" in statement
        and "ORDER BY analysis_jobs.available_at, analysis_jobs.id" in statement
    )


def test_sqlite_keeps_disposable_test_support():
    dialect = sqlite_dialect()
    statement = str(
        claim_statement(datetime(2026, 11, 6), dialect).compile(dialect=dialect)
    )
    assert "FOR UPDATE" not in statement and "SKIP LOCKED" not in statement
