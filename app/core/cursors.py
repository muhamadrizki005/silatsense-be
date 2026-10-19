"""Signed, user/filter-bound keyset cursors; never authorization credentials."""
import base64
from datetime import datetime, timezone
import hashlib
import hmac
import json
import re

from app.core.config import settings
from app.core.errors import DomainError


def _signature(payload):
    key = hmac.new(settings.jwt_secret.encode(), b"silatsense/history-cursor/v1", hashlib.sha256).digest()
    return hmac.new(key, payload, hashlib.sha256).digest()


def encode_cursor(user_id, filters, timestamp, session_id, *, scope="member-history"):
    body = {"v": 1, "scope": scope, "owner": str(user_id), "filters": filters,
            "at": timestamp.replace(tzinfo=timezone.utc).isoformat(), "id": str(session_id)}
    payload = json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(payload + _signature(payload)).decode().rstrip("=")


def decode_cursor(token, user_id, filters, *, scope="member-history"):
    try:
        if not token or len(token) > 4096 or not re.fullmatch(r"[A-Za-z0-9_-]+", token):
            raise ValueError()
        raw = base64.urlsafe_b64decode(token + "=" * (-len(token) % 4))
        payload, signature = raw[:-32], raw[-32:]
        if not hmac.compare_digest(signature, _signature(payload)):
            raise ValueError()
        body = json.loads(payload)
        if (body.get("v") != 1 or body.get("scope") != scope
                or body.get("owner") != str(user_id) or body.get("filters") != filters):
            raise ValueError()
        timestamp = datetime.fromisoformat(body["at"])
        if timestamp.tzinfo is None or timestamp.utcoffset().total_seconds() != 0:
            raise ValueError()
        sid = body["id"]
        if not isinstance(sid, str) or not sid.isascii() or not sid.isdigit() or not 1 <= int(sid) <= 2**63 - 1:
            raise ValueError()
        return timestamp.replace(tzinfo=None), int(sid)
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
        raise DomainError(422, "invalid_cursor", "Cursor tidak valid atau tidak sesuai pengguna/filter.")
