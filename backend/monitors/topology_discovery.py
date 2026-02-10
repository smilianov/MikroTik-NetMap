"""MNDP/LLDP topology discovery via RouterOS API.

Periodically queries /ip/neighbor on every device that has API credentials,
builds an adjacency graph, and detects topology changes (new devices, new
links, removed links).  Supports both REST (port 443) and Classic (port 8728)
API modes.
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from mikrotik.client import create_client
from models import (
    DeviceConfig,
    DeviceType,
    DiscoveredDevice,
    DiscoveredLink,
    LinkType,
    Position,
)

logger = logging.getLogger(__name__)

# Persistence file for discovered topology (survives restarts).
PERSISTENCE_FILE = Path(__file__).resolve().parent.parent.parent / "config" / "discovered_topology.json"

# Interface name patterns to determine link type.
_WIRELESS_PATTERNS = ("wlan", "wifi", "cap")
_VPN_PATTERNS = ("l2tp", "ipsec", "wg", "ovpn", "sstp", "pptp", "gre", "vxlan")


def _infer_link_type(interface_name: str) -> LinkType:
    """Infer link type from interface name."""
    lower = interface_name.lower()
    if any(p in lower for p in _WIRELESS_PATTERNS):
        return LinkType.WIRELESS
    if any(p in lower for p in _VPN_PATTERNS):
        return LinkType.VPN
    return LinkType.WIRED


def _infer_device_type(board: str, platform: str) -> str:
    """Guess device type from board/platform info."""
    b = board.lower()
    if "ccr" in b or "rb" in b or "hex" in b or "hap" in b:
        return DeviceType.ROUTER.value
    if "crs" in b or "css" in b:
        return DeviceType.SWITCH.value
    if "cap" in b or "wap" in b or "cube" in b or "disc" in b:
        return DeviceType.AP.value
    if platform.lower() != "mikrotik":
        return DeviceType.OTHER.value
    return DeviceType.ROUTER.value


def _make_link_id(a_dev: str, a_if: str, b_dev: str, b_if: str) -> str:
    """Create a canonical link ID (sorted so A:x-B:y == B:y-A:x)."""
    left = f"{a_dev}:{a_if}"
    right = f"{b_dev}:{b_if}"
    if left > right:
        left, right = right, left
    return f"{left}-{right}"


class TopologyDiscovery:
    """Discovers network topology by querying /ip/neighbor on MikroTik devices.

    Follows the PingMonitor pattern: async sweep loop with callback.
    """

    def __init__(
        self,
        devices: list[DeviceConfig],
        interval: int = 300,
        auto_add_devices: bool = False,
        auto_add_links: bool = True,
        on_update: Callable[..., Any] | None = None,
    ) -> None:
        # Only query devices that have API credentials.
        self.devices = [d for d in devices if d.password]
        self.interval = interval
        self.auto_add_devices = auto_add_devices
        self.auto_add_links = auto_add_links
        self.on_update = on_update

        # All configured device names (for determining which neighbors are "new").
        self._configured_names: set[str] = {d.name for d in devices}
        self._configured_hosts: set[str] = {d.host for d in devices}

        # Discovered state.
        self.discovered_devices: dict[str, DiscoveredDevice] = {}
        self.discovered_links: dict[str, DiscoveredLink] = {}

        # Device positions for auto-layout.
        self._device_positions: dict[str, Position] = {
            d.name: d.position for d in devices
        }

        self._running = False
        self._task: asyncio.Task[None] | None = None

        # Restore previous discoveries from disk.
        self._load_persistence()

    def _load_persistence(self) -> None:
        """Load previously discovered topology from JSON file."""
        if not PERSISTENCE_FILE.exists():
            return
        try:
            with open(PERSISTENCE_FILE, encoding="utf-8") as f:
                data = json.load(f)
            for d in data.get("devices", []):
                dev = DiscoveredDevice(**d)
                self.discovered_devices[dev.name] = dev
                self._device_positions[dev.name] = dev.position
            for ln in data.get("links", []):
                link = DiscoveredLink(**ln)
                self.discovered_links[link.id] = link
            logger.info(
                "Restored %d discovered devices, %d links from %s",
                len(self.discovered_devices),
                len(self.discovered_links),
                PERSISTENCE_FILE,
            )
        except Exception:
            logger.warning("Failed to load discovery persistence file", exc_info=True)

    def _save_persistence(self) -> None:
        """Save discovered topology to JSON file."""
        try:
            data = {
                "devices": [
                    d.model_dump(mode="json") for d in self.discovered_devices.values()
                ],
                "links": [
                    ln.model_dump(mode="json", by_alias=True)
                    for ln in self.discovered_links.values()
                ],
                "last_sweep": datetime.now(timezone.utc).isoformat(),
            }
            PERSISTENCE_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(PERSISTENCE_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, default=str)
        except Exception:
            logger.warning("Failed to save discovery persistence", exc_info=True)

    async def _query_device(
        self, device: DeviceConfig
    ) -> list[dict[str, Any]]:
        """Query /ip/neighbor on a single device. Returns raw neighbor list."""
        client = create_client(
            host=device.host,
            username=device.username,
            password=device.password,
            port=device.port,
            api_type=device.api_type,
            timeout=15.0,
        )
        try:
            neighbors = await client.get_neighbors()
            logger.info(
                "Device %s (%s via %s) returned %d neighbors",
                device.name, device.host, device.api_type, len(neighbors),
            )
            return [
                {
                    "local_device": device.name,
                    "local_interface": n.get("interface-name") or n.get("interface", ""),
                    "remote_identity": n.get("identity", ""),
                    "remote_address": n.get("address", ""),
                    "remote_mac": n.get("mac-address", ""),
                    "remote_platform": n.get("platform", ""),
                    "remote_board": n.get("board", ""),
                }
                for n in neighbors
                if n.get("identity") or n.get("address")
            ]
        except Exception:
            logger.warning(
                "Discovery failed for %s (%s via %s)",
                device.name, device.host, device.api_type, exc_info=True,
            )
            return []
        finally:
            await client.close()

    def _auto_position(self, parent_name: str, index: int, total: int) -> Position:
        """Calculate auto-position for a discovered device around its parent."""
        parent_pos = self._device_positions.get(parent_name, Position())
        radius = 150
        angle = (2 * math.pi * index / max(total, 1)) - math.pi / 2
        return Position(
            x=round(parent_pos.x + radius * math.cos(angle)),
            y=round(parent_pos.y + radius * math.sin(angle)),
        )

    async def _sweep(self) -> dict[str, Any]:
        """Query all devices, build topology, detect changes.

        Returns a dict with keys: added_devices, added_links, removed_links.
        """
        now = datetime.now(timezone.utc)

        # Collect all half-links from neighbor tables.
        tasks = [self._query_device(dev) for dev in self.devices]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        all_half_links: list[dict[str, Any]] = []
        for r in results:
            if isinstance(r, list):
                all_half_links.extend(r)
            elif isinstance(r, Exception):
                logger.warning("Discovery sweep exception: %s", r)

        if not all_half_links:
            logger.debug("Discovery sweep: no neighbors found")
            return {"added_devices": [], "added_links": [], "removed_links": []}

        # Group half-links by remote device identity for cross-matching.
        # Key: (local_device, remote_identity)
        by_local_remote: dict[tuple[str, str], dict] = {}
        # Track new device candidates (neighbors not in config).
        new_device_candidates: dict[str, dict] = {}

        for hl in all_half_links:
            remote_id = hl["remote_identity"]
            if not remote_id:
                # Use MAC or IP as fallback identity.
                remote_id = hl.get("remote_mac") or hl.get("remote_address", "")
            if not remote_id:
                continue

            key = (hl["local_device"], remote_id)
            by_local_remote[key] = hl

            # Track potential new devices.
            if (
                remote_id not in self._configured_names
                and remote_id not in self.discovered_devices
                and hl.get("remote_address")
            ):
                new_device_candidates[remote_id] = hl

        # Build full links by matching half-links.
        new_links: dict[str, DiscoveredLink] = {}

        for (local_dev, remote_id), hl in by_local_remote.items():
            local_if = hl["local_interface"]

            # Check if the remote also reported seeing us.
            reverse_key = (remote_id, local_dev)
            reverse_hl = by_local_remote.get(reverse_key)

            if reverse_hl:
                remote_if = reverse_hl["local_interface"]
            else:
                remote_if = "auto"

            link_id = _make_link_id(local_dev, local_if, remote_id, remote_if)

            if link_id in new_links:
                continue

            link_type = _infer_link_type(local_if)

            existing = self.discovered_links.get(link_id)
            first_seen = existing.first_seen if existing else now

            new_links[link_id] = DiscoveredLink(
                id=link_id,
                from_device=f"{local_dev}:{local_if}",
                to_device=f"{remote_id}:{remote_if}",
                speed=1000,
                type=link_type,
                first_seen=first_seen,
                last_seen=now,
            )

        # Detect changes.
        old_link_ids = set(self.discovered_links.keys())
        new_link_ids = set(new_links.keys())

        added_link_ids = new_link_ids - old_link_ids
        removed_link_ids = old_link_ids - new_link_ids

        # Handle new devices (if auto_add_devices enabled).
        added_devices: list[DiscoveredDevice] = []
        if self.auto_add_devices:
            # Count new neighbors per parent for positioning.
            parent_new_counts: dict[str, int] = {}
            for name, hl in new_device_candidates.items():
                parent = hl["local_device"]
                parent_new_counts[parent] = parent_new_counts.get(parent, 0) + 1

            parent_indices: dict[str, int] = {}
            for name, hl in new_device_candidates.items():
                parent = hl["local_device"]
                idx = parent_indices.get(parent, 0)
                parent_indices[parent] = idx + 1
                total = parent_new_counts[parent]

                position = self._auto_position(parent, idx, total)

                dev = DiscoveredDevice(
                    name=name,
                    host=hl["remote_address"],
                    mac=hl.get("remote_mac", ""),
                    platform=hl.get("remote_platform", ""),
                    board=hl.get("remote_board", ""),
                    discovered_by=parent,
                    discovered_on=hl["local_interface"],
                    first_seen=now,
                    last_seen=now,
                    position=position,
                )
                self.discovered_devices[name] = dev
                self._device_positions[name] = position
                self._configured_names.add(name)
                added_devices.append(dev)
        else:
            # Even if not auto-adding, update last_seen on known discovered devices.
            for name in new_device_candidates:
                if name in self.discovered_devices:
                    self.discovered_devices[name].last_seen = now

        # Update link state.
        self.discovered_links = new_links

        # Build change report.
        added_links = [new_links[lid] for lid in added_link_ids]
        removed_links = list(removed_link_ids)

        logger.info(
            "Discovery sweep: %d half-links, %d full links (%d new, %d removed), %d new devices",
            len(all_half_links),
            len(new_links),
            len(added_links),
            len(removed_links),
            len(added_devices),
        )

        # Persist to disk.
        self._save_persistence()

        return {
            "added_devices": added_devices,
            "added_links": added_links,
            "removed_links": removed_links,
        }

    async def _loop(self) -> None:
        """Main discovery loop."""
        if not self.devices:
            logger.info("TopologyDiscovery: no devices with credentials, skipping")
            return

        logger.info(
            "TopologyDiscovery started: %d queryable devices, interval=%ds",
            len(self.devices),
            self.interval,
        )

        # Run first sweep immediately.
        while self._running:
            changes = await self._sweep()

            if self.on_update and (
                changes["added_devices"]
                or changes["added_links"]
                or changes["removed_links"]
            ):
                try:
                    result = self.on_update(changes)
                    if asyncio.iscoroutine(result):
                        await result
                except Exception:
                    logger.exception("on_update callback error")

            await asyncio.sleep(self.interval)

    def start(self) -> None:
        """Start topology discovery as a background task."""
        self._running = True
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        """Stop topology discovery."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("TopologyDiscovery stopped")
