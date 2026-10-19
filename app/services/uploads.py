from pathlib import Path
from tempfile import TemporaryDirectory
from fastapi import HTTPException, UploadFile
from app.core.config import settings
from app.services.analysis import EvaluationService
from app.services.video import InvalidVideo
from app.repositories.evaluations import EvaluationRepository

ALLOWED = {
    ".mp4": {"video/mp4", "application/octet-stream"},
    ".mov": {"video/quicktime", "video/mp4", "application/octet-stream"},
    ".webm": {"video/webm", "application/octet-stream"},
}


def evaluate_upload(db, user, movement, video: UploadFile):
    suffix = Path(video.filename or "").suffix.lower()
    try:
        if suffix not in ALLOWED or video.content_type not in ALLOWED[suffix]:
            raise HTTPException(415, "Gunakan video MP4, MOV, atau WebM.")
        with TemporaryDirectory(prefix="silatsense-") as directory:
            path = Path(directory) / ("upload" + suffix)
            size = 0
            with path.open("wb") as target:
                while chunk := video.file.read(1024 * 1024):
                    size += len(chunk)
                    if size > settings.max_video_mb * 1024 * 1024:
                        raise HTTPException(413, "Ukuran video melebihi batas upload.")
                    target.write(chunk)
            if not size:
                raise HTTPException(422, "Video kosong.")
            repository = EvaluationRepository(db)
            result = EvaluationService().analyze(
                path, movement, repository.profiles(movement)
            )
            return repository.save(user.id, result)
    except InvalidVideo as exc:
        raise HTTPException(422, str(exc))
    except FileNotFoundError:
        raise HTTPException(
            503, "Model pose belum tersedia. Jalankan setup model pada backend."
        )
    finally:
        video.file.close()
