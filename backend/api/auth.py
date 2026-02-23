"""Auth API endpoints: login, logout, session check."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel

router = APIRouter(prefix="/api/auth", tags=["auth"])

_app_state: dict[str, Any] = {}


def set_app_state(state: dict[str, Any]) -> None:
    global _app_state
    _app_state = state


class LoginBody(BaseModel):
    username: str
    password: str


@router.post("/login")
async def login(body: LoginBody, response: Response):
    """Authenticate via Grafana and create a session."""
    session_mgr = _app_state.get("session_manager")
    auth_enabled = _app_state.get("auth_enabled", False)

    if not auth_enabled or not session_mgr:
        return {"ok": True, "message": "Auth disabled"}

    session = await session_mgr.login(body.username, body.password)
    if not session:
        response.status_code = 401
        return {"ok": False, "error": "Invalid credentials"}

    response.set_cookie(
        key="netmap_session",
        value=session.token,
        httponly=True,
        samesite="strict",
        path="/",
        max_age=session_mgr.session_ttl,
    )
    return {
        "ok": True,
        "username": session.username,
        "role": session.role,
    }


@router.post("/logout")
async def logout(request: Request, response: Response):
    """Destroy the current session."""
    session_mgr = _app_state.get("session_manager")
    token = request.cookies.get("netmap_session")

    if session_mgr and token:
        session_mgr.logout(token)

    response.delete_cookie(
        key="netmap_session",
        httponly=True,
        samesite="strict",
        path="/",
    )
    return {"ok": True}


@router.get("/me")
async def get_me(request: Request, response: Response):
    """Check current session and return user info."""
    auth_enabled = _app_state.get("auth_enabled", False)
    if not auth_enabled:
        return {"authenticated": True, "auth_enabled": False, "role": "Admin"}

    # Check proxy auth header first (set by nginx auth_request).
    header_user = request.headers.get("X-Auth-User")
    if header_user:
        roles = request.headers.get("X-Auth-Roles", "").split(",")
        return {
            "authenticated": True,
            "auth_enabled": True,
            "proxy_auth": True,
            "username": header_user,
            "roles": roles,
            "role": "admin" if "admin" in roles else "viewer",
        }

    session_mgr = _app_state.get("session_manager")
    token = request.cookies.get("netmap_session")
    session = session_mgr.validate(token) if session_mgr else None

    if not session:
        response.status_code = 401
        return {"authenticated": False}

    return {
        "authenticated": True,
        "auth_enabled": True,
        "username": session.username,
        "role": session.role,
    }
