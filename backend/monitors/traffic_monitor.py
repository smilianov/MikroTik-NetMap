"""Interface traffic monitor via RouterOS API.

Periodically queries /interface on devices with API credentials,
computes bandwidth utilisation from byte counter deltas.
Follows the PingMonitor pattern: async sweep loop with callback.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any, Callable

from mikrotik.client import create_client
from models import DeviceConfig

logger = logging.getLogger(__name__)


@dataclass
class _InterfaceCounters:
    """Snapshot of byte counters for one interface."""

    rx_bytes: int = 0
    tx_bytes: int = 0
    timestamp: float = 0.0  # time.monotonic()


class TrafficMonitor:
    """Collects per-interface traffic stats from MikroTik devices.

    Queries ``get_interfaces()`` on devices with API credentials every
    ``interval`` seconds, computes Δ bytes → bps between consecutive
    sweeps, and calls ``on_update`` with the result.
    """

    def __init__(
        self,
        devices: list[DeviceConfig],
        interval: int = 10,
        on_update: Callable[..., Any] | None = None,
        api_defaults: dict[str, Any] | None = None,
    ) -> None:
        # Query devices that have API credentials (password or SSH key),
        # or all devices when api_defaults provides a password.
        _defaults = api_defaults or {}
        has_default_password = bool(_defaults.get("password"))
        eligible = [
            d for d in devices
            if d.password or d.ssh_key_file or has_default_password
        ]
        # Apply api_defaults to devices that lack explicit credentials.
        self.devices = []
        for d in eligible:
            if not d.password and not d.ssh_key_file and has_default_password:
                d = d.model_copy(update={
                    "username": _defaults.get("username", d.username),
                    "password": _defaults["password"],
                    "api_type": _defaults.get("api_type", d.api_type),
                    "port": _defaults.get("port") or d.port,
                })
            self.devices.append(d)
        self.interval = interval
        self.on_update = on_update

        # Previous sweep counters: device_name → interface_name → counters.
        self._prev: dict[str, dict[str, _InterfaceCounters]] = {}

        self._running = False
        self._task: asyncio.Task[None] | None = None
        self._tracked_names: set[str] = {d.name for d in self.devices}

        # Latest computed traffic — sent to newly connecting WebSocket clients.
        self.latest_traffic: dict[str, dict[str, dict[str, Any]]] = {}

    def add_device(self, device: DeviceConfig) -> None:
        """Dynamically add a device for traffic collection (e.g. newly discovered)."""
        if device.name in self._tracked_names:
            return
        if not device.password and not device.ssh_key_file:
            return
        self.devices.append(device)
        self._tracked_names.add(device.name)
        logger.info("TrafficMonitor: added device %s (%s)", device.name, device.host)

    # ------------------------------------------------------------------
    # Device query
    # ------------------------------------------------------------------

    async def _query_device(
        self, device: DeviceConfig
    ) -> tuple[str, list[dict[str, Any]]]:
        """Query /interface on a single device."""
        client = create_client(
            host=device.host,
            username=device.username,
            password=device.password,
            port=device.port,
            api_type=device.api_type,
            timeout=15.0,
            ssh_key_file=device.ssh_key_file,
        )
        try:
            interfaces = await client.get_interfaces()
            return (device.name, interfaces)
        except Exception:
            logger.warning(
                "Traffic query failed for %s (%s via %s)",
                device.name,
                device.host,
                device.api_type,
                exc_info=True,
            )
            return (device.name, [])
        finally:
            await client.close()

    # ------------------------------------------------------------------
    # Sweep
    # ------------------------------------------------------------------

    async def _sweep(self) -> dict[str, dict[str, dict[str, Any]]] | None:
        """Query all devices, compute bps deltas.

        Returns ``None`` on the first sweep (no previous data to compare).
        """
        now = time.monotonic()

        tasks = [self._query_device(dev) for dev in self.devices]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        current: dict[str, dict[str, _InterfaceCounters]] = {}
        traffic: dict[str, dict[str, dict[str, Any]]] = {}
        has_deltas = False

        for r in results:
            if isinstance(r, Exception):
                logger.warning("Traffic sweep exception: %s", r)
                continue

            device_name, interfaces = r
            current[device_name] = {}
            traffic[device_name] = {}

            for iface in interfaces:
                if_name = iface.get("name", "")
                if not if_name:
                    continue

                rx_bytes = int(iface.get("rx-byte", 0) or 0)
                tx_bytes = int(iface.get("tx-byte", 0) or 0)
                running = str(iface.get("running", "true")).lower() == "true"

                current[device_name][if_name] = _InterfaceCounters(
                    rx_bytes=rx_bytes,
                    tx_bytes=tx_bytes,
                    timestamp=now,
                )

                # Compute delta from previous sweep.
                prev = self._prev.get(device_name, {}).get(if_name)
                if prev and prev.timestamp > 0:
                    elapsed = now - prev.timestamp
                    if elapsed > 0 and running:
                        rx_delta = max(0, rx_bytes - prev.rx_bytes)
                        tx_delta = max(0, tx_bytes - prev.tx_bytes)
                        rx_bps = (rx_delta * 8) / elapsed
                        tx_bps = (tx_delta * 8) / elapsed
                        traffic[device_name][if_name] = {
                            "rx_bps": round(rx_bps, 1),
                            "tx_bps": round(tx_bps, 1),
                        }
                        has_deltas = True

        self._prev = current

        if not has_deltas:
            return None

        self.latest_traffic = traffic
        return traffic

    # ------------------------------------------------------------------
    # Loop / lifecycle
    # ------------------------------------------------------------------

    async def _loop(self) -> None:
        """Main traffic collection loop."""
        if not self.devices:
            logger.info("TrafficMonitor: no devices with credentials, skipping")
            return

        logger.info(
            "TrafficMonitor started: %d devices, interval=%ds",
            len(self.devices),
            self.interval,
        )

        while self._running:
            traffic = await self._sweep()

            if traffic and self.on_update:
                try:
                    result = self.on_update(traffic)
                    if asyncio.iscoroutine(result):
                        await result
                except Exception:
                    logger.exception("on_update callback error")

            await asyncio.sleep(self.interval)

    def start(self) -> None:
        """Start the traffic monitor as a background task."""
        self._running = True
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        """Stop the traffic monitor."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("TrafficMonitor stopped")
