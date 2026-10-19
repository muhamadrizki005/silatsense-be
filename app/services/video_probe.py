"""Internal CLI: decode the entire video before accepting an asynchronous job."""
import json
import math
from pathlib import Path
import sys

from app.services.processes import constrain_child


def inspect_video(path, suffix, limits):
    import cv2
    with Path(path).open("rb") as source:
        header = source.read(4096)
    if header.startswith(b"\x1aE\xdf\xa3") and b"webm" in header.lower():
        mime = "video/webm"
    elif len(header) >= 12 and header[4:8] in {b"ftyp", b"moov", b"mdat", b"wide", b"free"}:
        mime = "video/quicktime" if header[8:12] == b"qt  " or suffix == ".mov" else "video/mp4"
    else:
        raise ValueError("invalid_video")
    if (suffix == ".webm") != (mime == "video/webm"):
        raise ValueError("invalid_video")
    capture = cv2.VideoCapture(str(path))
    try:
        if not capture.isOpened():
            raise ValueError("invalid_video")
        capture.set(cv2.CAP_PROP_ORIENTATION_AUTO, 1)
        fps, count = capture.get(cv2.CAP_PROP_FPS), capture.get(cv2.CAP_PROP_FRAME_COUNT)
        width, height = capture.get(cv2.CAP_PROP_FRAME_WIDTH), capture.get(cv2.CAP_PROP_FRAME_HEIGHT)
        if not all(math.isfinite(value) and value > 0 for value in (fps, count, width, height)) or fps > 240:
            raise ValueError("invalid_video")
        if count / fps > limits["seconds"]:
            raise ValueError("video_too_long")
        def dimensions_valid(w, h):
            return max(w, h) <= limits["long"] and min(w, h) <= limits["short"]
        if not dimensions_valid(width, height):
            raise ValueError("video_resolution_exceeded")
        actual = 0
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            height, width = frame.shape[:2]
            if not dimensions_valid(width, height):
                raise ValueError("video_resolution_exceeded")
            actual += 1
            if actual / fps > limits["seconds"]:
                raise ValueError("video_too_long")
        if actual == 0 or actual + 1 < count:
            raise ValueError("invalid_video")
        return {"durationSeconds": actual / fps, "width": int(width), "height": int(height), "mimeType": mime}
    finally:
        capture.release()


def main():
    constrain_child()
    request = json.load(sys.stdin)
    try:
        result = inspect_video(request["path"], request["suffix"], request["limits"])
    except (ValueError, OSError):
        print(json.dumps({"error": "invalid_video"}))
        return 1
    print(json.dumps(result, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
