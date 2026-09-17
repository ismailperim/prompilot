"""Login, logout and auth status."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import Field

from app.auth.middleware import COOKIE_NAME, AuthState
from app.models import CamelModel

router = APIRouter(prefix="/api/auth", tags=["auth"])


class AuthStatus(CamelModel):
    enabled: bool
    authenticated: bool


class LoginRequest(CamelModel):
    password: str = Field(min_length=1, max_length=512)


def _state(request: Request) -> AuthState:
    return request.app.state.auth


@router.get("", response_model=AuthStatus)
async def status(request: Request) -> AuthStatus:
    state = _state(request)
    return AuthStatus(enabled=state.enabled, authenticated=state.authenticated(request))


@router.post("/login", response_model=AuthStatus)
async def login(body: LoginRequest, request: Request, response: Response) -> AuthStatus:
    state = _state(request)
    if not state.enabled:
        return AuthStatus(enabled=False, authenticated=True)
    client = request.client.host if request.client else "?"
    if state.throttled(client):
        raise HTTPException(status_code=429, detail="Too many attempts. Wait 30 seconds.")
    if not state.check_password(body.password):
        state.record_failure(client)
        raise HTTPException(status_code=401, detail="Wrong password.")
    response.set_cookie(
        COOKIE_NAME,
        state.signer.issue(),
        max_age=int(state.signer.ttl),
        httponly=True,
        samesite="lax",
        secure=state.cookie_secure,
        path="/",
    )
    return AuthStatus(enabled=True, authenticated=True)


@router.post("/logout", response_model=AuthStatus)
async def logout(request: Request, response: Response) -> AuthStatus:
    state = _state(request)
    response.delete_cookie(COOKIE_NAME, path="/")
    return AuthStatus(enabled=state.enabled, authenticated=not state.enabled)
