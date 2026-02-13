"""Async MikroTik SSH client using key-based authentication.

Connects via SSH and executes RouterOS CLI commands, parsing the
terse output format into structured dicts (same interface as
MikroTikClient and MikroTikClassicClient).

Usage:
    client = MikroTikSSHClient(host="10.0.0.1", username="admin",
                                key_file="/app/config/id_rsa")
    neighbors = await client.get_neighbors()
    await client.close()
"""

from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class MikroTikSSHClient:
    """Async SSH client for MikroTik RouterOS devices.

    Uses key-based or password authentication via asyncssh.
    Executes CLI commands and parses terse output.
    """

    def __init__(
        self,
        host: str,
        username: str = "admin",
        password: str = "",
        key_file: str = "",
        port: int = 22,
        timeout: float = 15.0,
    ) -> None:
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.key_file = key_file
        self.timeout = timeout
        self._conn = None

    async def _connect(self) -> None:
        """Establish SSH connection."""
        import asyncssh

        connect_opts: dict[str, Any] = {
            "host": self.host,
            "port": self.port,
            "username": self.username,
            "known_hosts": None,  # MikroTik devices rarely in known_hosts
            "login_timeout": self.timeout,
        }

        if self.key_file:
            key_path = Path(self.key_file)
            if not key_path.exists():
                raise FileNotFoundError(f"SSH key file not found: {self.key_file}")
            connect_opts["client_keys"] = [str(key_path)]
            connect_opts["password"] = None
        elif self.password:
            connect_opts["password"] = self.password

        self._conn = await asyncssh.connect(**connect_opts)

    async def _run_command(self, command: str) -> str:
        """Execute a single CLI command and return output."""
        if not self._conn:
            await self._connect()

        result = await asyncio.wait_for(
            self._conn.run(command),
            timeout=self.timeout,
        )
        return result.stdout or ""

    @staticmethod
    def _parse_terse(output: str) -> list[dict[str, str]]:
        """Parse RouterOS terse output format into list of dicts.

        Terse output format example:
          0 interface-name=ether1 address=10.0.0.2 mac-address=AA:BB:CC:DD:EE:FF
          1 interface-name=ether2 address=10.0.0.3

        Each line represents a record. Key=value pairs are space-separated.
        Values containing spaces are quoted.
        """
        records: list[dict[str, str]] = []
        for line in output.strip().splitlines():
            line = line.strip()
            if not line:
                continue

            record: dict[str, str] = {}
            # Strip leading index (e.g., " 0 " or " 1 R ")
            # Match: optional spaces, optional digits, optional flags, then key=value pairs
            cleaned = re.sub(r"^\s*\d+\s*[A-Z]*\s*", "", line)

            # Parse key=value pairs (handles quoted values with spaces)
            for match in re.finditer(r'([\w.-]+)=("(?:[^"\\]|\\.)*"|[^\s]*)', cleaned):
                key = match.group(1)
                value = match.group(2)
                # Strip quotes if present
                if value.startswith('"') and value.endswith('"'):
                    value = value[1:-1]
                record[key] = value

            if record:
                records.append(record)
        return records

    async def get(self, path: str) -> list[dict[str, Any]]:
        """Query a RouterOS resource path via SSH CLI.

        Translates API paths to CLI commands:
          'ip/neighbor'    → '/ip/neighbor/print terse'
          'interface'      → '/interface/print terse'
          'system/resource' → '/system/resource/print'
        """
        cli_path = "/" + path.strip("/")
        command = f"{cli_path}/print terse"
        output = await self._run_command(command)

        # Map terse key names to REST API key names for compatibility.
        records = self._parse_terse(output)
        return [self._normalize_keys(r) for r in records]

    @staticmethod
    def _normalize_keys(record: dict[str, str]) -> dict[str, str]:
        """Normalize RouterOS CLI key names to match REST API format.

        CLI uses dot-separated names (interface.name), REST uses hyphens
        (interface-name). We keep the original format since both are
        handled downstream.
        """
        return record

    async def get_neighbors(self) -> list[dict[str, Any]]:
        """Query /ip/neighbor for MNDP/LLDP discovered neighbors."""
        return await self.get("ip/neighbor")

    async def get_interfaces(self) -> list[dict[str, Any]]:
        """Query /interface for all interface stats."""
        return await self.get("interface")

    async def get_ethernet_interfaces(self) -> list[dict[str, Any]]:
        """Query /interface/ethernet for physical port speeds."""
        return await self.get("interface/ethernet")

    async def get_system_resource(self) -> dict[str, Any]:
        """Query /system/resource for CPU, memory, uptime."""
        result = await self.get("system/resource")
        return result[0] if result else {}

    async def close(self) -> None:
        """Close the SSH connection."""
        if self._conn:
            self._conn.close()
            self._conn = None
