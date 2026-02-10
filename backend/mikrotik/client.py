"""Async MikroTik RouterOS API client.

Lightweight async wrapper using httpx for the REST API.
Designed to query /ip/neighbor, /interface, /system/resource, etc.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class MikroTikClient:
    """Async REST client for RouterOS 7.1+ devices."""

    def __init__(
        self,
        host: str,
        username: str = "admin",
        password: str = "",
        port: int = 443,
        ssl_verify: bool = False,
        timeout: float = 10.0,
    ) -> None:
        self.host = host
        self.base_url = f"https://{host}:{port}/rest"
        self._auth = (username, password)
        self._client = httpx.AsyncClient(
            auth=self._auth,
            verify=ssl_verify,
            timeout=timeout,
        )

    async def get(self, path: str) -> list[dict[str, Any]]:
        """GET /rest/<path> and return parsed JSON."""
        url = f"{self.base_url}/{path.strip('/')}"
        try:
            response = await self._client.get(url)
            response.raise_for_status()
            data = response.json()
            return [data] if isinstance(data, dict) else data
        except httpx.HTTPStatusError as exc:
            logger.error("API error %d: %s", exc.response.status_code, url)
            raise
        except httpx.RequestError as exc:
            logger.error("Connection error: %s — %s", url, exc)
            raise

    async def get_neighbors(self) -> list[dict[str, Any]]:
        """Query /ip/neighbor for MNDP/LLDP discovered neighbors."""
        return await self.get("ip/neighbor")

    async def get_interfaces(self) -> list[dict[str, Any]]:
        """Query /interface for all interface stats."""
        return await self.get("interface")

    async def get_system_resource(self) -> dict[str, Any]:
        """Query /system/resource for CPU, memory, uptime."""
        result = await self.get("system/resource")
        return result[0] if result else {}

    async def close(self) -> None:
        await self._client.aclose()
