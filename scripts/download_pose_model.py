from pathlib import Path
from urllib.request import urlopen
import hashlib
from app.core.config import settings

URL = "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task"


def main():
    target = Path(settings.pose_model_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with urlopen(URL, timeout=120) as response:
        data = response.read()
    if len(data) < 1000000:
        raise RuntimeError("Unexpected model response")
    target.write_bytes(data)
    print(f"{target}: sha256={hashlib.sha256(data).hexdigest()}")


if __name__ == "__main__":
    main()
