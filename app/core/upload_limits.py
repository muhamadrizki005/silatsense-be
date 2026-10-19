"""Bound multipart spooling before FastAPI constructs UploadFile objects."""
from uuid import uuid4

from starlette.formparsers import MultiPartException
from starlette.responses import JSONResponse

from app.core.config import settings


class UploadBodyLimit:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] != "POST" or scope["path"].rstrip("/") != "/api/v1/member/sessions":
            return await self.app(scope, receive, send)
        limit = settings.max_video_mb * 1024 * 1024 + 1024 * 1024
        exceeded, sent = False, False
        total = 0
        response = JSONResponse({"detail": "Body upload melebihi batas ukuran.", "code": "upload_too_large",
                                 "requestId": scope.get("state", {}).get("request_id", str(uuid4()))},
                                status_code=413, headers={"Cache-Control": "no-store"})
        for key, value in scope["headers"]:
            if key.lower() == b"content-length" and value.isdigit() and int(value) > limit:
                return await response(scope, receive, send)

        async def bounded_receive():
            nonlocal exceeded, total
            message = await receive()
            total += len(message.get("body", b""))
            if total > limit:
                exceeded = True
                # Starlette closes parser temporary files on MultiPartException.
                raise MultiPartException("Upload body limit exceeded")
            return message

        async def bounded_send(message):
            nonlocal sent
            if exceeded:
                if not sent:
                    sent = True
                    await response(scope, receive, send)
                return
            await send(message)
        return await self.app(scope, bounded_receive, bounded_send)
