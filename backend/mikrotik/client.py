"""Async MikroTik RouterOS API client.

Supports three connection modes:
  - REST (httpx, HTTPS port 443) — RouterOS 7.1+
  - Classic (routeros_api, port 8728) — RouterOS 6.49+
  - SSH (asyncssh, port 22) — any RouterOS version, supports key auth

All expose the same async interface: get(), get_neighbors(),
get_interfaces(), get_ethernet_interfaces(), get_bridge_hosts(), close().
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# Hosts for which an unencrypted/unverified-connection warning was already
# logged (clients are re-created every sweep — warn once per host).
_warned_hosts: set[str] = set()


def _warn_once(key: str, message: str, *args: Any) -> None:
    if key not in _warned_hosts:
        _warned_hosts.add(key)
        logger.warning(message, *args)


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
        if not ssl_verify:
            _warn_once(
                f"rest:{host}",
                "TLS certificate verification disabled for REST connection to %s "
                "— credentials are exposed to MITM attacks (set ssl_verify: true)",
                host,
            )
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

    async def get_ethernet_interfaces(self) -> list[dict[str, Any]]:
        """Query /interface/ethernet for physical port speeds."""
        return await self.get("interface/ethernet")

    async def get_bridge_hosts(self) -> list[dict[str, Any]]:
        """Query /interface/bridge/host for learned MAC locations."""
        return await self.get("interface/bridge/host")

    async def get_system_resource(self) -> dict[str, Any]:
        """Query /system/resource for CPU, memory, uptime."""
        result = await self.get("system/resource")
        return result[0] if result else {}

    async def close(self) -> None:
        await self._client.aclose()


class MikroTikClassicClient:
    """Async wrapper around routeros_api for Classic API (port 8728).

    The routeros_api library is synchronous, so all calls are wrapped
    in asyncio.to_thread() to avoid blocking the event loop.
    """

    def __init__(
        self,
        host: str,
        username: str = "admin",
        password: str = "",
        port: int = 8728,
        timeout: float = 15.0,
        use_ssl: bool = False,
        plaintext_login: bool = True,
        ssl_verify: bool = False,
        ssl_verify_hostname: bool = True,
    ) -> None:
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.timeout = timeout
        self.use_ssl = use_ssl
        self.plaintext_login = plaintext_login
        self.ssl_verify = ssl_verify
        self.ssl_verify_hostname = ssl_verify_hostname
        self._connection = None
        self._api = None
        if not use_ssl:
            _warn_once(
                f"classic:{host}",
                "Classic API connection to %s is not encrypted — credentials are "
                "sent in plaintext (set use_ssl: true with the api-ssl service)",
                host,
            )
        elif not ssl_verify:
            _warn_once(
                f"classic:{host}",
                "TLS certificate verification disabled for Classic API connection "
                "to %s — credentials are exposed to MITM attacks "
                "(set ssl_verify: true)",
                host,
            )

    def _connect_sync(self) -> None:
        """Synchronous connect (run in thread)."""
        import routeros_api

        self._connection = routeros_api.RouterOsApiPool(
            host=self.host,
            username=self.username,
            password=self.password,
            port=self.port,
            use_ssl=self.use_ssl,
            ssl_verify=self.ssl_verify,
            ssl_verify_hostname=self.ssl_verify_hostname,
            plaintext_login=self.plaintext_login,
        )
        self._connection.socket_timeout = self.timeout
        self._api = self._connection.get_api()

    def _get_sync(self, path: str) -> list[dict[str, Any]]:
        """Synchronous GET (run in thread)."""
        if not self._api:
            self._connect_sync()
        resource = self._api.get_resource(path)
        return resource.get()

    def _close_sync(self) -> None:
        """Synchronous close (run in thread)."""
        if self._connection:
            try:
                self._connection.disconnect()
            except Exception:
                pass
            self._connection = None
            self._api = None

    async def get(self, path: str) -> list[dict[str, Any]]:
        """Query a RouterOS resource path. Path uses slashes: 'ip/neighbor'."""
        # Classic API uses /ip/neighbor format.
        ros_path = "/" + path.strip("/")
        return await asyncio.to_thread(self._get_sync, ros_path)

    async def get_neighbors(self) -> list[dict[str, Any]]:
        """Query /ip/neighbor for MNDP/LLDP discovered neighbors."""
        return await self.get("ip/neighbor")

    async def get_interfaces(self) -> list[dict[str, Any]]:
        """Query /interface for all interface stats."""
        return await self.get("interface")

    async def get_ethernet_interfaces(self) -> list[dict[str, Any]]:
        """Query /interface/ethernet for physical port speeds."""
        return await self.get("interface/ethernet")

    async def get_bridge_hosts(self) -> list[dict[str, Any]]:
        """Query /interface/bridge/host for learned MAC locations."""
        return await self.get("interface/bridge/host")

    async def get_system_resource(self) -> dict[str, Any]:
        """Query /system/resource for CPU, memory, uptime."""
        result = await self.get("system/resource")
        return result[0] if result else {}

    async def close(self) -> None:
        await asyncio.to_thread(self._close_sync)


def create_client(
    host: str,
    username: str = "admin",
    password: str = "",
    port: int | None = None,
    api_type: str = "rest",
    timeout: float = 15.0,
    ssh_key_file: str = "",
    use_ssl: bool = False,
    ssl_verify: bool = False,
    ssl_verify_hostname: bool = True,
    known_hosts: str = "",
) -> "MikroTikClient | MikroTikClassicClient | MikroTikSSHClient":
    """Factory: create the right client based on api_type."""
    if api_type == "ssh":
        from mikrotik.ssh_client import MikroTikSSHClient

        return MikroTikSSHClient(
            host=host,
            username=username,
            password=password,
            key_file=ssh_key_file,
            port=port or 22,
            timeout=timeout,
            known_hosts=known_hosts,
        )
    elif api_type == "classic":
        return MikroTikClassicClient(
            host=host,
            username=username,
            password=password,
            port=port or 8728,
            timeout=timeout,
            use_ssl=use_ssl,
            ssl_verify=ssl_verify,
            ssl_verify_hostname=ssl_verify_hostname,
        )
    else:
        return MikroTikClient(
            host=host,
            username=username,
            password=password,
            port=port or 443,
            ssl_verify=ssl_verify,
            timeout=timeout,
        )
