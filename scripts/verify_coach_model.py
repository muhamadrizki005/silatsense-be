"""Verify private Coach artifact, pose model and dependency compatibility offline."""

import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path

from app.core.config import settings
from app.services.coach_analysis import load_reference


def verify(model_path, checksum, pose_path):
    model = load_reference(model_path, checksum)
    pose_checksum = hashlib.sha256(Path(pose_path).read_bytes()).hexdigest()
    signature = model["extractionSignature"]
    if pose_checksum != signature["poseModelSha256"]:
        raise ValueError("pose_model_checksum_mismatch")
    if settings.pose_model_sha256 and pose_checksum != settings.pose_model_sha256:
        raise ValueError("configured_pose_checksum_mismatch")
    for package, version in signature["versions"].items():
        if importlib.metadata.version(package) != version:
            raise ValueError("extraction_dependency_version_mismatch: " + package)
    return {
        "status": "ok",
        "referenceSha256": checksum,
        "poseModelSha256": pose_checksum,
        "movementIds": sorted(model["profiles"]),
        "productionReady": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=settings.coach_reference_model_path)
    parser.add_argument("--sha256", default=settings.coach_reference_sha256)
    parser.add_argument("--pose-model", default=settings.pose_model_path)
    args = parser.parse_args()
    try:
        print(json.dumps(verify(args.model, args.sha256, args.pose_model)))
    except (
        OSError,
        ValueError,
        KeyError,
        TypeError,
        importlib.metadata.PackageNotFoundError,
    ) as error:
        parser.exit(2, "Worker model verification failed: " + str(error) + "\n")


if __name__ == "__main__":
    main()
