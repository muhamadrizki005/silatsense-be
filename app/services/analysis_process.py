"""Internal inference child, reusing the existing intelligence pipeline."""
import hashlib
import json
from pathlib import Path
import sys

from app.services.processes import constrain_child


def execute(request):
    from app.core.config import settings
    from app.intelligence.contracts import ANALYZER_VERSION, FEATURE_VERSION
    from app.services.analysis import EvaluationService
    from app.services.video import InvalidVideo
    config = request["config"]
    if config["analyzerVersion"] != ANALYZER_VERSION or config["featureVersion"] != FEATURE_VERSION:
        return {"error": "analyzer_version_unavailable", "transient": False}
    path = Path(config["modelPath"])
    if not path.is_file():
        return {"error": "model_unavailable", "transient": False}
    if hashlib.sha256(path.read_bytes()).hexdigest() != config["modelChecksum"]:
        return {"error": "model_version_unavailable", "transient": False}
    profiles = []
    for snapshot in request["references"]:
        serialized = json.dumps(snapshot["profile"], sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        if hashlib.sha256(serialized).hexdigest() != snapshot["checksum"]:
            return {"error": "analysis_failed", "transient": False}
        profiles.append(snapshot["profile"])
    settings.pose_model_path = str(path)
    settings.sample_fps, settings.max_video_seconds = config["sampleFps"], config["maxSeconds"]
    try:
        return {"result": EvaluationService().analyze(Path(request["video"]), request["movement"], profiles)}
    except InvalidVideo:
        return {"error": "invalid_video", "transient": False}
    except OSError:
        return {"error": "analysis_failed", "transient": True}


def main():
    constrain_child()
    try:
        response = execute(json.load(sys.stdin))
        print(json.dumps(response, allow_nan=False))
    except Exception:
        print(json.dumps({"error": "analysis_failed", "transient": False}))


if __name__ == "__main__":
    main()
