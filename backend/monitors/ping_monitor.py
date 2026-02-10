"""Async ICMP ping monitor with 2-second resolution."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Callable

from icmplib import async_ping, ICMPLibError

from models import DeviceConfig, PingState

logger = logging.getLogger(__name__)


class PingMonitor:
    """Continuously pings all configured devices and maintains their state.

    Pings are sent every ``interval`` seconds.  Results are stored in
    ``self.states`` (keyed by device name) and forwarded to an optional
    callback after each sweep.
    """

    def __init__(
        self,
        devices: list[DeviceConfig],
        interval: float = 2.0,
        timeout: float = 1.0,
        on_update: Callable[[list[PingState]], Any] | None = None,
    ) -> None:
        self.devices = devices
        self.interval = interval
        self.timeout = timeout
        self.on_update = on_update
        self.states: dict[str, PingState] = {}
        self._running = False
        self._task: asyncio.Task[None] | None = None

        # Initialise state for every device.
        for dev in devices:
            self.states[dev.name] = PingState(device_id=dev.name)

    async def _ping_device(self, device: DeviceConfig) -> PingState:
        """Ping a single device and return its updated state."""
        state = self.states[device.name]
        try:
            result = await async_ping(
                device.host,
                count=1,
                timeout=self.timeout,
                privileged=False,  # Uses UDP fallback — no root needed
            )
            if result.is_alive:
                state.last_seen = datetime.now(timezone.utc)
                state.rtt_ms = result.avg_rtt
                state.is_alive = True
            else:
                state.is_alive = False
                state.rtt_ms = None
        except (ICMPLibError, OSError) as exc:
            logger.debug("Ping %s (%s) failed: %s", device.name, device.host, exc)
            state.is_alive = False
            state.rtt_ms = None
        return state

    async def _sweep(self) -> list[PingState]:
        """Ping all devices concurrently and return updated states."""
        tasks = [self._ping_device(dev) for dev in self.devices]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        updated: list[PingState] = []
        for r in results:
            if isinstance(r, PingState):
                updated.append(r)
            elif isinstance(r, Exception):
                logger.warning("Ping task exception: %s", r)

        return updated

    async def _loop(self) -> None:
        """Main monitor loop."""
        logger.info(
            "PingMonitor started: %d devices, interval=%.1fs",
            len(self.devices),
            self.interval,
        )
        while self._running:
            updated = await self._sweep()
            if self.on_update:
                try:
                    result = self.on_update(updated)
                    if asyncio.iscoroutine(result):
                        await result
                except Exception:
                    logger.exception("on_update callback error")
            await asyncio.sleep(self.interval)

    def start(self) -> None:
        """Start the ping monitor as a background task."""
        self._running = True
        self._task = asyncio.create_task(self._loop())

    def add_device(self, device: DeviceConfig) -> None:
        """Dynamically add a device to the ping cycle (used by topology discovery)."""
        if device.name not in self.states:
            self.devices.append(device)
            self.states[device.name] = PingState(device_id=device.name)
            logger.info("PingMonitor: added device %s (%s)", device.name, device.host)

    def remove_device(self, device_id: str) -> None:
        """Remove a device from the ping cycle."""
        self.devices = [d for d in self.devices if d.name != device_id]
        self.states.pop(device_id, None)
        logger.info("PingMonitor: removed device %s", device_id)

    async def stop(self) -> None:
        """Stop the ping monitor."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("PingMonitor stopped")
