"""Requires a session (or API token) for every ``/api`` route when auth is enabled."""

from __future__ import annotations

import hmac
import time
from collections import defaultdict

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from app.auth.sessions import SessionSigner

COOKIE_NAME = "prompilot_session"
OPEN_PREFIXES = ("/api/auth", "/healthz", "/openapi.json", "/docs", "/redoc")


class AuthState:
    """Everything the auth middleware and router share."""

    def __init__(
        self,
        *,
        password: str | None,
        api_token: str | None,
        signer: SessionSigner,
        cookie_secure: bool,
    ) -> None:
        self.password = password
        self.api_token = api_token
        self.signer = signer
        self.cookie_secure = cookie_secure
        self._failures: dict[str, list[float]] = defaultdict(list)

    @property
    def enabled(self) -> bool:
        return bool(self.password)

    def check_password(self, candidate: str) -> bool:
        return bool(self.password) and hmac.compare_digest(candidate, self.password or "")

    def check_token(self, candidate: str) -> bool:
        return bool(self.api_token) and hmac.compare_digest(candidate, self.api_token or "")

    # A small brake on password guessing: 5 failures per client → 30 s pause.
    def throttled(self, client: str, now: float | None = None) -> bool:
        now = now or time.time()
        recent = [t for t in self._failures[client] if now - t < 30]
        self._failures[client] = recent
        return len(recent) >= 5

    def record_failure(self, client: str, now: float | None = None) -> None:
        self._failures[client].append(now or time.time())

    def authenticated(self, request: Request) -> bool:
        if not self.enabled:
            return True
        header = request.headers.get("authorization", "")
        if header.startswith("Bearer ") and self.check_token(header[7:].strip()):
            return True
        return self.signer.verify(request.cookies.get(COOKIE_NAME)) is not None


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        state: AuthState = request.app.state.auth
        path = request.url.path
        guarded = path.startswith("/api") and not path.startswith(OPEN_PREFIXES)
        if guarded and not state.authenticated(request):
            return JSONResponse(status_code=401, content={"detail": "Sign in to continue."})
        return await call_next(request)
