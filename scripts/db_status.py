"""One SELECT 1, sanitized diagnostics, no queue claim/storage probe/mutation."""

import argparse
import json

from app.core.error_metadata import safe_error_metadata
from scripts.process_env import load_private_env


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file")
    args = parser.parse_args()
    engine = None
    try:
        load_private_env(args.env_file)
        from sqlalchemy import text
        from app.db.session import engine
        from app.core.config import settings

        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        result = {
            "status": "ok",
            "poolMode": settings.db_pool_mode,
            "maxConnectionsPerProcess": settings.db_pool_size + settings.db_max_overflow
            if settings.db_pool_mode == "queue" and engine.dialect.name != "sqlite"
            else None,
        }
        code = 0
    except Exception as error:
        result = {"status": "unavailable", **safe_error_metadata(error)}
        code = 1
    finally:
        if engine is not None:
            engine.dispose()  # Only our own short-lived diagnostic engine.
    print(json.dumps(result))
    raise SystemExit(code)


if __name__ == "__main__":
    main()
