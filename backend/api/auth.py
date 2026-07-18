"""Auth API endpoints: login, logout, session check."""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel

router = APIRouter(prefix="/api/auth", tags=["auth"])

_app_state: dict[str, Any] = {}


def set_app_state(state: dict[str, Any]) -> None:
    global _app_state
    _app_state = state


class LoginRateLimiter:
    """In-memory per-client-IP sliding-window limiter for login attempts.

    Per-process only: with multiple uvicorn workers each worker keeps its
    own counters, and all counters reset on restart.
    """

    def __init__(self, max_attempts: int = 5, window_seconds: float = 60.0) -> None:
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self._attempts: dict[str, list[float]] = {}

    def is_limited(self, key: str) -> float:
        """Return seconds to wait if the client is over the limit, else 0.0."""
        now = time.monotonic()
        self._evict_stale(now)
        attempts = self._current_attempts(key, now)
        if len(attempts) >= self.max_attempts:
            self._attempts[key] = attempts
            return max(1.0, self.window_seconds - (now - attempts[0]))
        return 0.0

    def record_failure(self, key: str) -> None:
        """Record one failed login attempt for the client."""
        now = time.monotonic()
        self._evict_stale(now)
        attempts = self._current_attempts(key, now)
        attempts.append(now)
        self._attempts[key] = attempts

    def reset(self, key: str) -> None:
        """Clear the client's counter (called on successful login)."""
        self._attempts.pop(key, None)

    def _current_attempts(self, key: str, now: float) -> list[float]:
        return [
            t for t in self._attempts.get(key, [])
            if now - t < self.window_seconds
        ]

    def _evict_stale(self, now: float) -> None:
        """Drop keys with no attempts in the current window (bounds memory)."""
        stale = [
            k for k, ts in self._attempts.items()
            if not ts or now - ts[-1] >= self.window_seconds
        ]
        for k in stale:
            del self._attempts[k]


_login_limiter = LoginRateLimiter()


def _client_ip(request: Request, cfg: Any) -> str:
    """Best-effort client IP for rate limiting.

    When trusted proxy headers are enabled, only the value our own proxy
    added is trusted: X-Real-IP if present, else the rightmost
    X-Forwarded-For entry. Leftmost XFF entries are client-controlled and
    would let an attacker rotate into a fresh rate-limit bucket.
    """
    if cfg is not None and getattr(cfg, "auth_trust_headers", False):
        real_ip = request.headers.get("x-real-ip", "").strip()
        if real_ip:
            return real_ip
        forwarded = request.headers.get("x-forwarded-for", "")
        if forwarded:
            return forwarded.split(",")[-1].strip()
    return request.client.host if request.client else "unknown"


def _cookie_secure(request: Request, cfg: Any) -> bool:
    """Resolve the cookie Secure flag: auth.cookie_secure override, else auto.

    Auto mode sets Secure when the request arrived over HTTPS, honoring
    X-Forwarded-Proto when trusted proxy headers are enabled.
    """
    override = getattr(cfg, "auth_cookie_secure", None) if cfg is not None else None
    if override is not None:
        return bool(override)
    scheme = request.url.scheme
    if cfg is not None and getattr(cfg, "auth_trust_headers", False):
        scheme = request.headers.get("x-forwarded-proto", scheme)
    return scheme == "https"


class LoginBody(BaseModel):
    username: str
    password: str


@router.post("/login")
async def login(body: LoginBody, request: Request, response: Response):
    """Authenticate via Grafana and create a session."""
    session_mgr = _app_state.get("session_manager")
    auth_enabled = _app_state.get("auth_enabled", False)

    if not auth_enabled or not session_mgr:
        return {"ok": True, "message": "Auth disabled"}

    cfg = _app_state.get("config")
    client_key = _client_ip(request, cfg)
    retry_after = _login_limiter.is_limited(client_key)
    if retry_after > 0:
        response.status_code = 429
        response.headers["Retry-After"] = str(int(retry_after))
        return {"ok": False, "error": "Too many login attempts — try again later"}

    session = await session_mgr.login(body.username, body.password)
    if not session:
        _login_limiter.record_failure(client_key)
        response.status_code = 401
        return {"ok": False, "error": "Invalid credentials"}

    # Successful login: clear any accumulated failures for this client.
    _login_limiter.reset(client_key)

    response.set_cookie(
        key="netmap_session",
        value=session.token,
        httponly=True,
        samesite="strict",
        secure=_cookie_secure(request, cfg),
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

    # Check proxy auth header (set by nginx auth_request) — only when trust is configured.
    cfg = _app_state.get("config")
    if cfg and getattr(cfg, "auth_trust_headers", False):
        header_user = request.headers.get(
            getattr(cfg, "auth_header_user", "X-Auth-User")
        )
        if header_user:
            roles = [
                r.strip() for r in
                request.headers.get(
                    getattr(cfg, "auth_header_roles", "X-Auth-Roles"), ""
                ).split(",")
                if r.strip()
            ]
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
