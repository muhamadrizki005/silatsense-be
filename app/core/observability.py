"""HTTP metadata only: never log request bodies, headers, query strings or raw paths."""

import json
import logging
from time import perf_counter
from uuid import uuid4

logger = logging.getLogger("silatsense.http")
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)


class RequestLogMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        request_id = str(uuid4())
        scope.setdefault("state", {})["request_id"] = request_id
        started, status = perf_counter(), 500

        async def send_response(message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                headers = [
                    (key, value)
                    for key, value in message.get("headers", [])
                    if key.lower() != b"x-request-id"
                ]
                headers.append((b"x-request-id", request_id.encode()))
                if scope.get("path", "").startswith("/api/v1/auth/"):
                    headers = [
                        (key, value)
                        for key, value in headers
                        if key.lower() != b"cache-control"
                    ]
                    headers.append((b"cache-control", b"no-store"))
                message["headers"] = headers
            await send(message)

        try:
            await self.app(scope, receive, send_response)
        finally:
            route = scope.get("route")
            logger.info(
                json.dumps(
                    dict(
                        event="http_request",
                        requestId=request_id,
                        method=scope["method"],
                        route=getattr(route, "path", "unmatched"),
                        status=status,
                        durationMs=round((perf_counter() - started) * 1000, 2),
                    )
                )
            )
