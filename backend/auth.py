"""Session-based authentication via Grafana API validation."""

from __future__ import annotations

import logging
import secrets
import time
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)


@dataclass
class Session:
    """In-memory session record."""

    token: str
    username: str
    role: str  # "Admin", "Editor", "Viewer"
    grafana_id: int
    expires_at: float


class SessionManager:
    """In-memory session store with Grafana API validation."""

    def __init__(self, grafana_url: str, session_ttl: int = 28800) -> None:
        self.grafana_url = grafana_url.rstrip("/")
        self.session_ttl = session_ttl
        self._sessions: dict[str, Session] = {}

    async def login(self, username: str, password: str) -> Session | None:
        """Validate credentials against Grafana API. Returns Session or None."""
        try:
            async with httpx.AsyncClient(verify=False, timeout=10) as client:
                resp = await client.get(
                    f"{self.grafana_url}/api/user",
                    auth=(username, password),
                )
            if resp.status_code != 200:
                logger.info("Grafana auth failed for '%s': HTTP %d", username, resp.status_code)
                return None

            data = resp.json()
            grafana_id = data.get("id", 0)
            role = data.get("role", "Viewer")

            # If role not in /api/user response, fetch from org membership.
            if "role" not in data:
                org_role = await self._fetch_org_role(username, password)
                if org_role:
                    role = org_role

        except httpx.RequestError as exc:
            logger.error("Cannot reach Grafana at %s: %s", self.grafana_url, exc)
            return None

        token = secrets.token_hex(32)
        session = Session(
            token=token,
            username=username,
            role=role,
            grafana_id=grafana_id,
            expires_at=time.time() + self.session_ttl,
        )
        self._sessions[token] = session
        logger.info("Login: user=%s role=%s", username, role)
        return session

    async def _fetch_org_role(self, username: str, password: str) -> str | None:
        """Fetch user's role from Grafana org membership."""
        try:
            async with httpx.AsyncClient(verify=False, timeout=10) as client:
                resp = await client.get(
                    f"{self.grafana_url}/api/user/orgs",
                    auth=(username, password),
                )
            if resp.status_code == 200:
                orgs = resp.json()
                if orgs:
                    return orgs[0].get("role", "Viewer")
        except httpx.RequestError:
            pass
        return None

    def validate(self, token: str | None) -> Session | None:
        """Validate a session token. Returns Session or None."""
        self._cleanup()
        if not token:
            return None
        session = self._sessions.get(token)
        if session and session.expires_at > time.time():
            return session
        return None

    def logout(self, token: str | None) -> None:
        """Destroy a session."""
        if token and token in self._sessions:
            del self._sessions[token]

    def _cleanup(self) -> None:
        """Remove expired sessions."""
        now = time.time()
        expired = [k for k, v in self._sessions.items() if v.expires_at < now]
        for k in expired:
            del self._sessions[k]

    @property
    def active_count(self) -> int:
        self._cleanup()
        return len(self._sessions)
