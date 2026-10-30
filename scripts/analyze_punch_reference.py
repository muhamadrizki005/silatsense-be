"""Offline, local-only motion observations; no DB, API writes or model training."""

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import math
from pathlib import Path

import numpy as np

from app.intelligence.punch_diagnostics import (
    ELBOWS,
    elbow_observation,
    phase_at,
    summarize,
    validate_phases,
)


def file_hash(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def json_landmarks(points):
    if points is None:
        return None
    return [
        [float(value) if np.isfinite(value) else None for value in point]
        for point in points
    ]


def detect(extractor, rgb):
    """Reuse runtime detector setup, retaining raw world landmarks for diagnostics."""
    result = extractor.detector.detect(
        extractor.mp.Image(
            image_format=extractor.mp.ImageFormat.SRGB, data=np.ascontiguousarray(rgb)
        )
    )
    count = len(result.pose_landmarks)
    if count != 1:
        return None, None, count
    image = np.array([[p.x, p.y, p.z, p.visibility] for p in result.pose_landmarks[0]])
    world = (
        np.array([[p.x, p.y, p.z] for p in result.pose_world_landmarks[0]])
        if len(result.pose_world_landmarks) == 1
        else None
    )
    return image, world, count


def draw_preview(frame, image, observation):
    import cv2

    result = frame.copy()
    height, width = frame.shape[:2]
    cv2.putText(
        result,
        "DIAGNOSTIC ONLY - no correctness verdict",
        (12, 26),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.55,
        (0, 220, 255),
        1,
        cv2.LINE_AA,
    )
    cv2.putText(
        result,
        f"t={observation['timeSeconds']:.3f}s",
        (12, 50),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.55,
        (255, 255, 255),
        1,
        cv2.LINE_AA,
    )
    if image is not None:
        for number, (side, indices) in enumerate(ELBOWS.items()):
            measured = observation["elbows"][side]
            degrees = measured["imageAngleDeg"]
            if degrees is None:
                continue
            points = [
                (round(image[index, 0] * width), round(image[index, 1] * height))
                for index in indices
            ]
            for a, b in zip(points, points[1:]):
                cv2.line(result, a, b, (255, 220, 0), 2)
            for point in points:
                cv2.circle(result, point, 4, (255, 220, 0), -1)
            cv2.putText(
                result,
                f"{side}: 2D {degrees:.1f} deg",
                (12, 76 + number * 24),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                (255, 255, 255),
                1,
                cv2.LINE_AA,
            )
    return result


def render_plot(report, path):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    if path.exists():
        raise ValueError("Plot sudah ada; gunakan output baru")
    figure, axes = plt.subplots(2, 1, figsize=(10, 6), sharex=True)
    times = [frame["timeSeconds"] for frame in report["frames"]]
    for side, axis in zip(ELBOWS, axes):
        for key, label, style in [
            ("imageAngleDeg", "2D image projection", "-"),
            ("estimatedWorldAngleDeg", "3D model estimate", "--"),
        ]:
            values = [frame["elbows"][side][key] for frame in report["frames"]]
            axis.plot(
                times,
                [value if value is not None else np.nan for value in values],
                style,
                label=label,
            )
        axis.set_title(side.capitalize() + " elbow")
        axis.set_ylabel("Internal angle (deg)")
        axis.set_ylim(0, 185)
        axis.grid(alpha=0.25)
        axis.legend(loc="lower left", fontsize=8)
    axes[-1].set_xlabel("Approximate video time (seconds)")
    figure.suptitle("Diagnostic observations: neither curve is measured ground truth")
    figure.tight_layout()
    try:
        figure.savefig(path, dpi=140)
    finally:
        plt.close(figure)


def analyze(
    video,
    model,
    output,
    sample_fps=None,
    annotations=None,
    max_seconds=60,
    visibility=0.5,
):
    import cv2
    from app.intelligence.pose.mediapipe_extractor import MediaPipePoseExtractor

    if not video.is_file() or not model.is_file():
        raise ValueError("Video atau model pose belum tersedia")
    if output.exists():
        raise ValueError("Folder output sudah ada; gunakan nama run baru")
    if not math.isfinite(max_seconds) or max_seconds <= 0:
        raise ValueError("max-seconds harus positif")
    if sample_fps is not None and (not math.isfinite(sample_fps) or sample_fps <= 0):
        raise ValueError("sample-fps harus positif")
    if not math.isfinite(visibility) or not 0 <= visibility <= 1:
        raise ValueError("visibility harus antara 0 dan 1")
    capture = cv2.VideoCapture(str(video))
    extractor = None
    try:
        if not capture.isOpened():
            raise ValueError("Video tidak dapat dibaca")
        capture.set(cv2.CAP_PROP_ORIENTATION_AUTO, 1)
        fps, count = (
            capture.get(cv2.CAP_PROP_FPS),
            capture.get(cv2.CAP_PROP_FRAME_COUNT),
        )
        if (
            not math.isfinite(fps)
            or not 0 < fps <= 240
            or not math.isfinite(count)
            or count < 1
        ):
            raise ValueError("Metadata FPS/frame tidak valid")
        duration = count / fps
        if duration > max_seconds:
            raise ValueError("Durasi video melebihi batas eksperimen")
        segments = (
            validate_phases(
                json.loads(annotations.read_text(encoding="utf-8")), duration
            )
            if annotations
            else None
        )
        stride = max(1, round(fps / sample_fps)) if sample_fps else 1
        extractor = MediaPipePoseExtractor(str(model))
        frames, previews, index = [], [], 0
        selected = {
            round(position * (count - 1) / stride) * stride
            for position in np.linspace(0, 1, 6)
        }
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            if index / fps > max_seconds:
                raise ValueError("Video terdecode melebihi batas durasi")
            if index % stride == 0:
                height, width = frame.shape[:2]
                scale = min(1.0, 1280 / max(height, width))
                if scale < 1:
                    frame = cv2.resize(
                        frame, (round(width * scale), round(height * scale))
                    )
                height, width = frame.shape[:2]
                image, world, people = detect(
                    extractor, cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                )
                row = dict(
                    frameIndex=index,
                    timeSeconds=index / fps,
                    phase=phase_at(index / fps, segments),
                    peopleDetected=people,
                    imageLandmarks=json_landmarks(image),
                    estimatedWorldLandmarks=json_landmarks(world),
                    elbows={
                        side: elbow_observation(
                            image, world, side, width, height, visibility
                        )
                        for side in ELBOWS
                    },
                )
                if people != 1:
                    for result in row["elbows"].values():
                        result["reason"] = (
                            "multiple_people" if people > 1 else "pose_not_detected"
                        )
                frames.append(row)
                if index in selected:
                    previews.append((index, draw_preview(frame, image, row)))
            index += 1
        if index < int(count) - 1:
            raise ValueError(
                "Video berhenti decode sebelum jumlah frame metadata; periksa file"
            )
        summary = summarize(frames)
        report = dict(
            schemaVersion=1,
            experiment="pukulan-front-elbow-diagnostic-v1",
            createdAt=datetime.now(timezone.utc).isoformat(),
            sourceVideoSha256=file_hash(video),
            poseModelSha256=file_hash(model),
            movementSlug="pukulan",
            cameraView="front_as_input_assumption",
            video=dict(
                fps=fps,
                metadataFrameCount=int(count),
                decodedFrameCount=index,
                durationSeconds=duration,
            ),
            sampling=dict(
                stride=stride,
                timestampBasis="frame_index_divided_by_container_fps",
                runningMode="IMAGE_independent_frames_in_temporal_order",
                visibilityThreshold=visibility,
            ),
            versions={
                name: importlib.metadata.version(name)
                for name in ("numpy", "mediapipe", "opencv-contrib-python")
            },
            manualPhases=segments,
            summary=summary,
            frames=frames,
        )
        output.mkdir(parents=True)
        with (output / "observations.json").open("x", encoding="utf-8") as handle:
            json.dump(report, handle, indent=2, allow_nan=False)
        for frame_index, preview in previews:
            if not cv2.imwrite(str(output / f"frame-{frame_index:04d}.jpg"), preview):
                raise OSError("Gagal menyimpan preview")
        return report
    finally:
        capture.release()
        if extractor is not None:
            extractor.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument(
        "--model", type=Path, default=Path("artifacts/pose/pose_landmarker_lite.task")
    )
    parser.add_argument(
        "--output", type=Path, required=True, help="Use an ignored .cache/... directory"
    )
    parser.add_argument(
        "--sample-fps", type=float, help="Default: inspect every decoded frame"
    )
    parser.add_argument(
        "--annotations", type=Path, help="Optional manual phase intervals JSON"
    )
    parser.add_argument("--max-seconds", type=float, default=60)
    parser.add_argument("--visibility", type=float, default=0.5)
    parser.add_argument(
        "--plot",
        action="store_true",
        help="Save a diagnostic chart; no correctness colors",
    )
    args = parser.parse_args()
    try:
        report = analyze(
            args.video,
            args.model,
            args.output,
            args.sample_fps,
            args.annotations,
            args.max_seconds,
            args.visibility,
        )
        if args.plot:
            render_plot(report, args.output / "elbow-diagnostics.png")
    except (ValueError, OSError, ImportError) as error:
        parser.exit(2, str(error) + "\n")
    print(json.dumps(report["summary"], indent=2))
    print("Private observations and previews saved to: " + str(args.output))


if __name__ == "__main__":
    main()
