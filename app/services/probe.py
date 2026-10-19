import json
import subprocess
import sys
import tempfile

from app.core.config import settings
from app.core.errors import DomainError
from app.services.processes import ChildGuard, child_options


def probe_video(path, suffix):
    payload = {"path": str(path), "suffix": suffix, "limits": {
        "seconds": settings.max_video_seconds, "long": settings.max_video_dimension,
        "short": settings.max_video_short_dimension,
    }}
    with tempfile.TemporaryFile() as output:
        process = subprocess.Popen([sys.executable, "-m", "app.services.video_probe"],
                                   stdin=subprocess.PIPE, stdout=output, stderr=subprocess.DEVNULL,
                                   **child_options(settings.process_memory_mb))
        guard = None
        try:
            guard = ChildGuard(process, settings.process_memory_mb)
            process.communicate(json.dumps(payload).encode(), timeout=settings.video_probe_timeout_seconds)
            output.seek(0)
            result = json.loads(output.read(65536))
            if process.returncode != 0 or "error" in result:
                raise DomainError(422, "invalid_video", "Video tidak valid atau melebihi batas durasi/resolusi.")
            return result
        except subprocess.TimeoutExpired:
            raise DomainError(503, "video_validation_timeout", "Validasi video melampaui batas waktu.")
        except (ValueError, OSError):
            raise DomainError(503, "video_validation_unavailable", "Validasi video tidak tersedia.")
        finally:
            if process.poll() is None:
                process.kill()
            process.wait()
            if guard:
                guard.close()
