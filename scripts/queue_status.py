"""Read-only queue diagnostics; outputs counts/lease state, no personal data."""

import json
from sqlalchemy import select, func
from app.db.session import SessionLocal
from app.models.entities import AnalysisJob, now


def main():
    with SessionLocal() as db:
        counts = dict(
            db.execute(
                select(AnalysisJob.state, func.count()).group_by(AnalysisJob.state)
            ).all()
        )
        stale = db.scalar(
            select(func.count())
            .select_from(AnalysisJob)
            .where(AnalysisJob.state == "processing", AnalysisJob.lease_until <= now())
        )
    print(json.dumps({"queue": counts, "expiredLeases": stale}))


if __name__ == "__main__":
    main()
