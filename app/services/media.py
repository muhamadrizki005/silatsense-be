"""Private playback with per-chunk authorization and bounded reads."""
import re
import anyio

from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.core.errors import DomainError
from app.models.entities import CoachAssignment, MediaAsset, TrainingSession, User, now
from app.services.sessions import get_session
from app.services.storage import LocalStorage

CHUNK_SIZE = 256 * 1024


class PrivateVideoResponse(StreamingResponse):
    """Also cancel a slow/stalled stream, independent of its next chunk."""

    def __init__(self, *args, access_check, expiry, handle, **kwargs):
        super().__init__(*args, **kwargs)
        self.access_check, self.expiry, self.handle = access_check, expiry, handle

    async def __call__(self, scope, receive, send):
        try:
            async with anyio.create_task_group() as group:
                async def body():
                    try:
                        await super(PrivateVideoResponse, self).__call__(scope, receive, send)
                    finally:
                        group.cancel_scope.cancel()

                async def watch():
                    while True:
                        await anyio.sleep(0.5)
                        try:
                            allowed = await anyio.to_thread.run_sync(self.access_check, abandon_on_cancel=True)
                        except Exception:
                            allowed = False
                        if not allowed or now() >= self.expiry:
                            group.cancel_scope.cancel()
                            return

                async def deadline():
                    # Expiry must not wait for a slow DB authorization query.
                    await anyio.sleep(max(0, (self.expiry - now()).total_seconds()))
                    group.cancel_scope.cancel()

                group.start_soon(body)
                group.start_soon(watch)
                group.start_soon(deadline)
        finally:
            self.handle.close()


def byte_range(header, size):
    if header is None:
        return 0, size - 1, 200
    match = re.fullmatch(r"bytes=([0-9]*)-([0-9]*)", header)
    if not match or not any(match.groups()) or any(len(x) > 20 for x in match.groups()):
        raise ValueError("Invalid range")
    left, right = match.groups()
    if left:
        start, end = int(left), int(right) if right else size - 1
        if start >= size or end < start:
            raise ValueError("Unsatisfiable range")
        end = min(end, size - 1)
    else:
        suffix = int(right)
        if suffix <= 0:
            raise ValueError("Invalid suffix")
        start, end = max(0, size - suffix), size - 1
    return start, end, 206


def media_access(db, owner_id, value):
    session = get_session(db, owner_id, value)
    asset = db.scalar(select(MediaAsset).where(MediaAsset.session_id == session.id))
    if asset and asset.expires_at <= now():
        raise DomainError(410, "media_expired", "Masa simpan video telah berakhir.")
    if asset and (asset.deletion_requested_at or asset.deleted_at):
        raise DomainError(410, "media_deleted", "Video sudah dihapus.")
    if not asset:
        raise DomainError(410, "media_unavailable", "Video tidak tersedia.")
    return session, asset


def stream_allowed(factory, owner_id, auth_version, sid, asset_id, expires_at, actor_id=None, assignment_event_id=None):
    if now() >= expires_at:
        return False
    # New transaction every chunk: MySQL repeatable-read must not retain the
    # request's old snapshot after deletion/password revocation commits.
    with factory() as db:
        statement = select(MediaAsset.id).join(TrainingSession, TrainingSession.id == MediaAsset.session_id)
        if actor_id is None:
            statement = statement.join(User, User.id == TrainingSession.user_id)
        else:
            statement = statement.join(CoachAssignment, CoachAssignment.member_id == TrainingSession.user_id)
            statement = statement.join(User, User.id == CoachAssignment.coach_id).where(
                User.id == actor_id, CoachAssignment.event_id == assignment_event_id)
        statement = statement.where(
                MediaAsset.id == asset_id, TrainingSession.id == sid,
                TrainingSession.user_id == owner_id, TrainingSession.deleted_at.is_(None),
                MediaAsset.deleted_at.is_(None), MediaAsset.deletion_requested_at.is_(None),
                MediaAsset.expires_at > now(), User.role == ("COACH" if actor_id is not None else "MEMBER"), User.auth_version == auth_version,
            )
        return db.scalar(statement) is not None


def stream_chunks(handle, start, end, factory, owner_id, version, sid, asset_id, expiry, actor_id=None, assignment_event_id=None):
    try:
        handle.seek(start)
        remaining = end - start + 1
        while remaining > 0:
            chunk = handle.read(min(CHUNK_SIZE, remaining))
            if not chunk:
                return
            try:
                allowed = stream_allowed(factory, owner_id, version, sid, asset_id, expiry, actor_id, assignment_event_id)
            except Exception:
                return  # Fail closed on DB outage; do not log Bearer/path data.
            if not allowed:
                return
            if now() >= expiry:
                return
            remaining -= len(chunk)
            yield chunk
    finally:
        handle.close()


def playback(db, user, value, range_header, *, owner_id=None, assignment_event_id=None):
    owner, version = user.id if owner_id is None else owner_id, user.auth_version
    actor_id = user.id if owner_id is not None else None
    session, asset = media_access(db, owner, value)
    try:
        handle = LocalStorage().path(asset.storage_key).open("rb")
    except (OSError, ValueError):
        raise DomainError(410, "media_unavailable", "Video tidak tersedia.")
    try:
        import os
        size = os.fstat(handle.fileno()).st_size
        if size != asset.byte_size or size <= 0:
            raise DomainError(410, "media_unavailable", "Video tidak tersedia.")
        try:
            start, end, status = byte_range(range_header, size)
        except ValueError:
            error = DomainError(416, "invalid_range", "Range video tidak valid.")
            error.headers = {"Content-Range": f"bytes */{size}", "Accept-Ranges": "bytes"}
            raise error
        sid, aid, expiry, mime = session.id, asset.id, asset.expires_at, asset.mime_type
        factory = sessionmaker(bind=db.get_bind())
        db.rollback()  # Never hold the dependency transaction for a long stream.
        headers = {"Accept-Ranges": "bytes", "Content-Length": str(end - start + 1),
                   "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"}
        if status == 206:
            headers["Content-Range"] = f"bytes {start}-{end}/{size}"
        return PrivateVideoResponse(
            stream_chunks(handle, start, end, factory, owner, version, sid, aid, expiry, actor_id, assignment_event_id),
            status_code=status, media_type=mime, headers=headers,
            background=BackgroundTask(handle.close),
            access_check=lambda: stream_allowed(factory, owner, version, sid, aid, expiry, actor_id, assignment_event_id),
            expiry=expiry, handle=handle,
        )
    except BaseException:
        handle.close()
        raise
