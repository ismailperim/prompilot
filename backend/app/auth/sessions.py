"""Signed session tokens (no server-side session store needed)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class Session:
    issued_at: float
    expires_at: float


class SessionSigner:
    def __init__(self, secret: str, ttl_seconds: float) -> None:
        self._key = hashlib.sha256(("session:" + secret).encode()).digest()
        self.ttl = ttl_seconds

    def issue(self, now: float | None = None) -> str:
        now = now or time.time()
        payload = json.dumps(
            {"iat": now, "exp": now + self.ttl, "n": secrets.token_hex(8)}, separators=(",", ":")
        ).encode()
        body = base64.urlsafe_b64encode(payload).rstrip(b"=").decode()
        return f"{body}.{self._sign(body)}"

    def verify(self, token: str | None, now: float | None = None) -> Session | None:
        if not token or "." not in token:
            return None
        body, signature = token.rsplit(".", 1)
        if not hmac.compare_digest(self._sign(body), signature):
            return None
        try:
            padded = body + "=" * (-len(body) % 4)
            payload = json.loads(base64.urlsafe_b64decode(padded))
            issued, expires = float(payload["iat"]), float(payload["exp"])
        except (ValueError, KeyError, TypeError):
            return None
        if (now or time.time()) >= expires:
            return None
        return Session(issued_at=issued, expires_at=expires)

    def _sign(self, body: str) -> str:
        return hmac.new(self._key, body.encode(), hashlib.sha256).hexdigest()
