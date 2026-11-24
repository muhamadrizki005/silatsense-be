import argparse
from concurrent.futures import ThreadPoolExecutor
import logging
import os
import signal
from threading import Event

from scripts.process_env import load_private_env


def preflight():
    import json
    from sqlalchemy import text

    component = "configuration"
    try:
        from app.core.config import settings
        from app.db.session import SessionLocal
        from app.services.storage import get_storage
        from scripts.verify_coach_model import verify

        component = "model"
        if settings.analysis_mode == "coach-reference":
            verify(
                settings.coach_reference_model_path,
                settings.coach_reference_sha256,
                settings.pose_model_path,
            )
        component = "database"
        with SessionLocal() as db:
            if db.execute(text("SELECT 1")).scalar() != 1:
                raise ValueError("Database check failed")
            if set(
                db.execute(text("SELECT version_num FROM alembic_version")).scalars()
            ) != {"0008"}:
                raise ValueError("Migration required")
        component = "storage"
        get_storage().check()
    except Exception as error:
        from app.core.error_metadata import safe_error_metadata

        metadata = (
            safe_error_metadata(error)
            if component in {"configuration", "database"}
            else {}
        )
        print(
            json.dumps(
                {
                    "status": "not_ready",
                    "failedComponent": component,
                    "workerActive": False,
                    **metadata,
                }
            )
        )
        return False
    print(
        json.dumps(
            {
                "status": "ready",
                "analysisMode": settings.analysis_mode,
                "workerActive": False,
            }
        )
    )
    return True


def main():
    parser = argparse.ArgumentParser(description="Persistent MySQL analysis worker")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--env-file")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check model/DB/storage without claiming jobs",
    )
    args = parser.parse_args()
    try:
        load_private_env(args.env_file)
    except ValueError as error:
        parser.error(str(error))
    if args.check:
        raise SystemExit(0 if preflight() else 1)
    from app.core.config import settings
    from app.db.session import SessionLocal
    from app.services.worker import Worker

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    stop = Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())
    if args.once:
        Worker(SessionLocal, f"worker-{os.getpid()}-0", stop).run_once()
    else:
        with ThreadPoolExecutor(max_workers=settings.worker_concurrency) as pool:
            futures = [
                pool.submit(
                    Worker(SessionLocal, f"worker-{os.getpid()}-{i}", stop).run_forever
                )
                for i in range(settings.worker_concurrency)
            ]
            for future in futures:
                future.result()


if __name__ == "__main__":
    main()
