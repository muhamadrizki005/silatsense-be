import argparse
import logging
import signal
from threading import Event

from app.core.config import settings
from app.db.session import SessionLocal
from app.services.cleanup import cleanup_once


def main():
    parser = argparse.ArgumentParser(description="Expire private media and reconcile orphan uploads")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    stop = Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())
    if args.once:
        cleanup_once(SessionLocal)
        return
    while not stop.is_set():
        try:
            cleanup_once(SessionLocal)
        except Exception:
            logging.error("cleanup_iteration_failed")
        stop.wait(settings.cleanup_interval_seconds)


if __name__ == "__main__":
    main()
