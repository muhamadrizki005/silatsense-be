from pathlib import Path

ALLOWED = {
    ".mp4": {"video/mp4", "application/octet-stream"},
    ".mov": {"video/quicktime", "video/mp4", "application/octet-stream"},
    ".webm": {"video/webm", "application/octet-stream"},
}


class InvalidVideo(ValueError):
    pass


def sampled_frames(path: Path, sample_fps: float, max_seconds: int):
    # Load native video dependencies only in the process that decodes video.
    # Importing API upload constants must not require desktop/X11 libraries.
    import cv2

    capture = cv2.VideoCapture(str(path))
    try:
        if not capture.isOpened():
            raise InvalidVideo(
                "Video tidak dapat dibaca. Gunakan MP4, MOV, atau WebM yang valid."
            )
        fps = capture.get(cv2.CAP_PROP_FPS)
        count = capture.get(cv2.CAP_PROP_FRAME_COUNT)
        if fps <= 0 or fps > 240 or count <= 0:
            raise InvalidVideo("Metadata durasi/FPS video tidak valid.")
        if count / fps > max_seconds:
            raise InvalidVideo(f"Durasi video maksimum {max_seconds} detik.")
        # OpenCV FFmpeg honors rotation metadata via ORIENTATION_AUTO.
        capture.set(cv2.CAP_PROP_ORIENTATION_AUTO, 1)
        stride = max(1, round(fps / max(0.1, sample_fps)))
        index = 0
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            if index / fps > max_seconds:
                raise InvalidVideo("Video melebihi batas durasi.")
            if index % stride == 0:
                h, w = frame.shape[:2]
                if max(h, w) > 1280:
                    frame = cv2.resize(
                        frame,
                        (round(w * 1280 / max(h, w)), round(h * 1280 / max(h, w))),
                    )
                yield (
                    index,
                    round(index / fps, 3),
                    cv2.cvtColor(frame, cv2.COLOR_BGR2RGB),
                )
            index += 1
        if index == 0:
            raise InvalidVideo("Video tidak memiliki frame yang dapat dibaca.")
    finally:
        capture.release()
