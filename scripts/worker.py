import argparse
from concurrent.futures import ThreadPoolExecutor
import logging
import os
import signal
from threading import Event

from app.core.config import settings
from app.db.session import SessionLocal
from app.services.worker import Worker


def main():
    parser = argparse.ArgumentParser(description="Persistent MySQL analysis worker")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    stop = Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())
    if args.once:
        Worker(SessionLocal, f"worker-{os.getpid()}-0", stop).run_once()
    else:
        with ThreadPoolExecutor(max_workers=settings.worker_concurrency) as pool:
            futures = [pool.submit(Worker(SessionLocal, f"worker-{os.getpid()}-{i}", stop).run_forever)
                       for i in range(settings.worker_concurrency)]
            for future in futures:
                future.result()


if __name__ == "__main__":
    main()
