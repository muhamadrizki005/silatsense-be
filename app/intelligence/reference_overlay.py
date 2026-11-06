"""Private offline skeleton preview, driven only by explicit comparison colors."""

from pathlib import Path

import numpy as np

from app.intelligence.movement_video import file_hash

COLORS = {
    "green": (0, 200, 0),
    "yellow": (0, 220, 255),
    "red": (0, 0, 255),
    None: (150, 150, 150),
}


def render(video, observations, comparison, output):
    import cv2

    video, output = Path(video), Path(output)
    if output.exists():
        raise ValueError("Preview exists; choose a new output")
    if output.suffix.lower() != ".mp4":
        raise ValueError("Preview output must be .mp4")
    if comparison.get("status") != "compared" or not comparison.get("frames"):
        raise ValueError("No assessable comparison frames")
    if (
        file_hash(video) != observations["sourceVideoSha256"]
        or comparison["sourceVideoSha256"] != observations["sourceVideoSha256"]
    ):
        raise ValueError(
            "Video, observations and comparison must have matching source hashes"
        )
    if not any(row.get("imageLandmarks") is not None for row in observations["frames"]):
        raise ValueError(
            "Re-extract with reference_pipeline extract to retain overlay landmarks"
        )
    capture, writer = cv2.VideoCapture(str(video)), None
    created = False
    try:
        fps = capture.get(cv2.CAP_PROP_FPS)
        if not capture.isOpened() or not np.isfinite(fps) or fps <= 0:
            raise ValueError("Cannot read preview source")
        frames = observations["frames"]
        times = np.array([row["timeSeconds"] for row in frames])
        comparisons = comparison["frames"]
        comparison_times = np.array([row["timeSeconds"] for row in comparisons])
        index = 0
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            h, w = frame.shape[:2]
            if writer is None:
                output.parent.mkdir(parents=True, exist_ok=True)
                output.open("xb").close()
                created = True
                writer = cv2.VideoWriter(
                    str(output), cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h)
                )
                if not writer.isOpened():
                    raise ValueError("MP4 preview encoder unavailable")
            seconds = index / fps
            nearest = int(np.abs(times - seconds).argmin())
            measured = frames[nearest]
            selected = int(np.abs(comparison_times - seconds).argmin())
            aligned = comparisons[selected]
            points = measured.get("imageLandmarks")
            # Do not paint a stale pose or verdict through a missing interval.
            if points is not None and abs(times[nearest] - seconds) <= 0.15:
                edges = {}
                priority = {None: -1, "green": 0, "yellow": 1, "red": 2}
                for item in aligned["joints"].values():
                    fresh = abs(comparison_times[selected] - seconds) <= 0.15
                    name = item["color"] if fresh else None
                    for a, b in zip(
                        item["landmarkIndices"], item["landmarkIndices"][1:]
                    ):
                        edge = tuple(sorted((a, b)))
                        if edge not in edges or priority[name] > priority[edges[edge]]:
                            edges[edge] = name
                for (a, b), name in edges.items():
                    xy = [points[a][:2], points[b][:2]]
                    if any(v is None or not np.isfinite(v) for p in xy for v in p):
                        continue
                    pixels = [tuple(round(v * h) for v in p) for p in xy]
                    cv2.line(frame, *pixels, COLORS[name], 3, cv2.LINE_AA)
            caption = "EXPERIMENTAL - reference comparison; gray = unassessed"
            cv2.putText(
                frame,
                caption,
                (12, 25),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (255, 255, 255),
                1,
                cv2.LINE_AA,
            )
            writer.write(frame)
            index += 1
        if index != observations["video"]["decodedFrameCount"]:
            raise ValueError("Preview decode count differs from observations")
        return {"output": str(output), "frameCount": index, "experimental": True}
    except Exception:
        if writer is not None:
            writer.release()
            writer = None
        if created:
            output.unlink(missing_ok=True)
        raise
    finally:
        capture.release()
        if writer is not None:
            writer.release()
