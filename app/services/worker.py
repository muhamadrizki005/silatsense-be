import json
import logging
import subprocess
import sys
import tempfile
from pathlib import Path
from threading import Event
import time

from app.core.config import settings
from app.models.entities import now
from app.repositories.jobs import JobRepository
from app.services.processes import ChildGuard, child_options
from app.services.storage import get_storage
from app.services.probe import probe_video
from app.core.errors import DomainError

logger = logging.getLogger(__name__)


class Worker:
    def __init__(self, factory, worker_id, stop=None):
        self.jobs, self.worker_id = JobRepository(factory), worker_id
        self.stop = stop or Event()

    def run_once(self):
        claim = self.jobs.claim(self.worker_id)
        if claim is None:
            return False
        logger.info("job_started jobId=%s", claim.job_id)
        started = time.monotonic()
        try:
            self._run(claim)
        except OSError:
            self.jobs.fail(claim, "analysis_failed", transient=True)
        except (ValueError, KeyError):
            self.jobs.fail(claim, "analysis_failed")
        finally:
            logger.info(json.dumps({"event": "job_attempt_finished", "jobId": claim.job_id,
                "workerId": self.worker_id, "durationMs": round((time.monotonic() - started) * 1000, 2)}))
        return True

    def _run(self, claim):
        storage = get_storage()
        if not storage.exists(claim.storage_key):
            self.jobs.fail(claim, "media_unavailable")
            return
        download_started = heartbeat_at = time.monotonic()

        def progress():
            nonlocal heartbeat_at
            if time.monotonic() - download_started > settings.worker_job_timeout_seconds:
                raise DomainError(422, "analysis_timeout", "Download melampaui batas waktu.")
            if self.stop.is_set() or now() >= claim.expires_at:
                raise OSError("Download interrupted")
            if time.monotonic() - heartbeat_at >= settings.worker_heartbeat_seconds:
                if not self.jobs.heartbeat(claim):
                    raise OSError("Worker lease lost")
                heartbeat_at = time.monotonic()

        try:
            with storage.materialize(claim.storage_key, checksum=claim.checksum, progress=progress) as path:
                progress()
                if claim.config.get("remoteUpload"):
                    # Probe is bounded and keeps the same fenced lease alive.
                    if not self.jobs.heartbeat(claim):
                        return
                    metadata = probe_video(path, Path(claim.storage_key).suffix, progress=progress)
                    progress()
                    if not self.jobs.heartbeat(claim) or not self.jobs.validated_media(claim, metadata):
                        return
                self._analyze(claim, path)
        except DomainError as error:
            self.jobs.fail(claim, error.code, transient=error.status_code == 503)

    def _analyze(self, claim, path):
        config = dict(claim.config)
        if config.get("remoteUpload"):
            config["modelPath"] = str(Path(settings.pose_model_path).resolve())
        payload = {"video": str(path), "movement": claim.movement,
                   "references": claim.references, "config": config}
        with tempfile.TemporaryFile() as output:
            process = subprocess.Popen([sys.executable, "-m", "app.services.analysis_process"],
                                       stdin=subprocess.PIPE, stdout=output, stderr=subprocess.DEVNULL,
                                       **child_options(settings.process_memory_mb))
            guard = None
            try:
                guard = ChildGuard(process, settings.process_memory_mb)
                process.stdin.write(json.dumps(payload, allow_nan=False).encode())
                process.stdin.close()
                started, heartbeat_at = time.monotonic(), time.monotonic()
                while process.poll() is None:
                    if self.stop.is_set():
                        process.kill()
                        process.wait()
                        self.jobs.fail(claim, "worker_shutdown", transient=True)
                        return
                    if claim.expires_at <= now():
                        process.kill()
                        process.wait()
                        self.jobs.fail(claim, "media_expired")
                        return
                    if time.monotonic() - started > settings.worker_job_timeout_seconds:
                        process.kill()
                        process.wait()
                        self.jobs.fail(claim, "analysis_timeout")
                        return
                    if time.monotonic() - heartbeat_at >= settings.worker_heartbeat_seconds:
                        if not self.jobs.heartbeat(claim):
                            return
                        heartbeat_at = time.monotonic()
                    self.stop.wait(0.1)
                output.seek(0)
                raw = output.read(2 * 1024 * 1024 + 1)
                if process.returncode != 0 or len(raw) > 2 * 1024 * 1024:
                    self.jobs.fail(claim, "analysis_failed")
                    return
                result = json.loads(raw)
                if "error" in result:
                    self.jobs.fail(claim, result["error"], transient=result.get("transient", False))
                else:
                    self.jobs.complete(claim, result["result"])
            finally:
                if process.poll() is None:
                    process.kill()
                process.wait()
                if guard:
                    guard.close()

    def run_forever(self):
        while not self.stop.is_set():
            try:
                worked = self.run_once()
            except Exception:
                # DB outage: committed leases are recovered on restart/expiry.
                logger.error("worker_iteration_failed workerId=%s", self.worker_id)
                worked = False
            if not worked:
                self.stop.wait(settings.worker_poll_seconds)
