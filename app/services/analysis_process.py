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
    temporal = config.get("method") == "coach-reference-dtw"
    from app.intelligence.coach_contracts import ANALYZER_VERSION as COACH_VERSION, FEATURE_VERSION as COACH_FEATURES
    expected = (COACH_VERSION, COACH_FEATURES) if temporal else (ANALYZER_VERSION, FEATURE_VERSION)
    if (config["analyzerVersion"], config["featureVersion"]) != expected:
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
    try:
        if temporal:
            from app.services.coach_analysis import analyze, load_reference, ReferenceArtifactError
            try:
                model = load_reference(settings.coach_reference_model_path, config.get("referenceModelChecksum"))
                return {"result": analyze(Path(request["video"]), request["movement"], config["movementId"],
                    model, config["referenceModelChecksum"], path, config["maxSeconds"])}
            except ReferenceArtifactError as error:
                return {"error": error.code, "transient": False}
            except ValueError:
                return {"error": "analysis_failed", "transient": False}
        settings.pose_model_path = str(path)
        settings.sample_fps, settings.max_video_seconds = config["sampleFps"], config["maxSeconds"]
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
