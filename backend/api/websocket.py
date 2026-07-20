"""WebSocket connection manager for real-time state broadcasting."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages WebSocket connections and broadcasts state updates."""

    def __init__(self) -> None:
        self._connections: list[WebSocket] = []
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._connections.append(ws)
        logger.info("WebSocket connected (%d total)", len(self._connections))

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            if ws in self._connections:
                self._connections.remove(ws)
        logger.info("WebSocket disconnected (%d total)", len(self._connections))

    async def broadcast(self, message: dict[str, Any]) -> None:
        """Send a JSON message to all connected clients."""
        async with self._lock:
            connections = list(self._connections)
        if not connections:
            return

        payload = json.dumps(message, default=_json_default)

        async def _send(ws: WebSocket) -> WebSocket | None:
            try:
                await ws.send_text(payload)
            except Exception:
                return ws
            return None

        # Send outside the lock so one slow client can't stall other
        # broadcasts or connect/disconnect.
        results = await asyncio.gather(*(_send(ws) for ws in connections))
        dead = [ws for ws in results if ws is not None]

        if dead:
            async with self._lock:
                for ws in dead:
                    if ws in self._connections:
                        self._connections.remove(ws)
            logger.debug("Removed %d dead WebSocket connections", len(dead))

    @property
    def client_count(self) -> int:
        return len(self._connections)


def _json_default(obj: Any) -> Any:
    """JSON serialiser for datetime objects."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")
