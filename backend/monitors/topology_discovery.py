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
import re
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

# Tree layout constants.
TREE_VERTICAL_SPACING = 200
TREE_HORIZONTAL_SPACING = 200

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


def _gateway_score(board: str) -> int:
    """Score a board for switch-gateway likelihood.  Higher = more backbone.

    Only CRS/CSS boards score > 0.  SFP/SFP+/XG port counts push the score
    up — backbone switches (e.g. CRS317-1G-16S) outscore access switches
    (e.g. CRS326-24G-2S).
    """
    if not board:
        return 0
    b = board.upper()
    # Only consider switches (CRS/CSS) as potential gateways.
    if "CRS" not in b and "CSS" not in b:
        return 0
    score = 50  # Base score for being a switch.
    # SFP+ ports (10G fibre).
    m = re.search(r"(\d+)S\+", b)
    if m:
        score += int(m.group(1)) * 10
    # SFP ports (1G fibre) — but not SFP+ (already matched above).
    m = re.search(r"(\d+)S(?!\+|S)", b)
    if m:
        score += int(m.group(1)) * 6
    # XG ports (10G copper).
    m = re.search(r"(\d+)XG", b)
    if m:
        score += int(m.group(1)) * 10
    return score


def _make_link_id(a_dev: str, a_if: str, b_dev: str, b_if: str) -> str:
    """Create a canonical link ID (sorted so A:x-B:y == B:y-A:x)."""
    left = f"{a_dev}:{a_if}"
    right = f"{b_dev}:{b_if}"
    if left > right:
        left, right = right, left
    return f"{left}-{right}"


def _parse_speed(speed_str: str) -> int:
    """Parse MikroTik speed string to Mbps integer.

    Examples: "1Gbps"→1000, "10Gbps"→10000, "100Mbps"→100, "2.5Gbps"→2500.
    """
    if not speed_str:
        return 0
    s = speed_str.strip().upper()
    m = re.match(r"([\d.]+)\s*(G|M|K)?BPS", s)
    if not m:
        return 0
    val = float(m.group(1))
    unit = m.group(2) or "M"
    if unit == "G":
        return int(val * 1000)
    if unit == "K":
        return max(1, int(val / 1000))
    return int(val)


def _parse_advertise_speed(advertise: str) -> int:
    """Extract max speed from the ethernet advertise field.

    Example: '10M-baseT-full,100M-baseT-full,1G-baseT-full' → 1000.
    """
    if not advertise:
        return 0
    max_speed = 0
    for part in advertise.split(","):
        p = part.strip().upper()
        if "10G" in p or "10000M" in p:
            max_speed = max(max_speed, 10000)
        elif "5G" in p or "5000M" in p:
            max_speed = max(max_speed, 5000)
        elif "2.5G" in p or "2500M" in p:
            max_speed = max(max_speed, 2500)
        elif p.startswith("1G") or "1000M" in p:
            max_speed = max(max_speed, 1000)
        elif "100M" in p:
            max_speed = max(max_speed, 100)
        elif "10M" in p:
            max_speed = max(max_speed, 10)
    return max_speed


def _infer_interface_speed(if_name: str) -> int:
    """Infer speed from interface name when no data is available.

    SFP+ interfaces are typically 10G, SFP are 1G, etc.
    """
    lower = if_name.lower()
    if "sfp-sfpplus" in lower or "sfpplus" in lower or "xg" in lower:
        return 10000
    if "sfp" in lower:
        return 1000
    if "combo" in lower:
        return 1000
    return 0


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
        visibility_manager: Any | None = None,
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
        self.auto_add_devices = auto_add_devices
        self.auto_add_links = auto_add_links
        self.on_update = on_update
        self._visibility = visibility_manager
        self._api_defaults = api_defaults or {}

        # Track which device names/hosts we already query (to avoid duplicates).
        self._queryable_names: set[str] = {d.name for d in self.devices}

        # All configured device names (for determining which neighbors are "new").
        self._configured_names: set[str] = {d.name for d in devices}
        self._configured_hosts: set[str] = {d.host for d in devices}

        # Per-device interface speed map: {device_name: {interface_name: speed_mbps}}.
        self.interface_speeds: dict[str, dict[str, int]] = {}

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
        if self.discovered_devices:
            # Rebuild hierarchy from persisted data.
            self._infer_hierarchy_from_persisted()
            self._recalculate_tree_positions()
            self._save_persistence()
            # Add persisted discovered devices as queryable (for immediate first sweep).
            for dd in self.discovered_devices.values():
                self.add_queryable_device(dd.name, dd.host)

    def _make_device_config(self, name: str, host: str) -> DeviceConfig:
        """Build a DeviceConfig for a discovered device using api_defaults."""
        return DeviceConfig(
            name=name,
            host=host,
            username=self._api_defaults.get("username", "admin"),
            password=self._api_defaults.get("password", ""),
            api_type=self._api_defaults.get("api_type", "rest"),
            port=self._api_defaults.get("port"),
        )

    def add_queryable_device(self, name: str, host: str) -> None:
        """Add a discovered device to the queryable list using api_defaults.

        Only adds if api_defaults has a password and the device isn't already tracked.
        """
        if not self._api_defaults.get("password"):
            return
        if name in self._queryable_names:
            return
        dev = self._make_device_config(name, host)
        self.devices.append(dev)
        self._queryable_names.add(name)
        logger.info("Added queryable device: %s (%s)", name, host)

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

    def _infer_hierarchy_from_persisted(self) -> None:
        """Rebuild parent-child hierarchy from persisted discovered devices.

        Constructs synthetic half-links from persisted data so
        ``_infer_hierarchy`` can group by interface and pick gateways.
        """
        synthetic: list[dict[str, Any]] = []
        for dev in self.discovered_devices.values():
            synthetic.append({
                "local_device": dev.discovered_by
                    if dev.discovered_by in self._configured_names
                    else next(iter(self._configured_names), ""),
                "local_interface": dev.discovered_on,
                "remote_identity": dev.name,
                "remote_board": dev.board,
            })
        if not synthetic:
            return
        parent_map = self._infer_hierarchy(synthetic)
        for name, dev in self.discovered_devices.items():
            new_parent = parent_map.get(name)
            if new_parent and new_parent != dev.discovered_by:
                logger.info(
                    "Persisted hierarchy fix: %s parent %s → %s",
                    name, dev.discovered_by, new_parent,
                )
                dev.discovered_by = new_parent

    async def _query_device(
        self, device: DeviceConfig
    ) -> dict[str, Any]:
        """Query /ip/neighbor and /interface/ethernet on a single device.

        Returns {"neighbors": [...], "interfaces": [...]}.
        """
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
            neighbors = await client.get_neighbors()

            # Query ethernet interfaces for speed data (best-effort).
            eth_interfaces: list[dict[str, Any]] = []
            try:
                eth_interfaces = await client.get_ethernet_interfaces()
            except Exception:
                logger.debug(
                    "Ethernet interface query failed for %s (non-critical)",
                    device.name,
                )

            # Also query general /interface for SFP types (best-effort).
            all_interfaces: list[dict[str, Any]] = []
            try:
                all_interfaces = await client.get_interfaces()
            except Exception:
                pass

            # Merge SFP interfaces into eth_interfaces for speed inference.
            eth_names = {i.get("name", "") for i in eth_interfaces}
            for iface in all_interfaces:
                if_name = iface.get("name", "")
                if_type = iface.get("type", "")
                # Add SFP/SFP+ interfaces not already in ethernet list.
                if if_name and if_name not in eth_names and "sfp" in if_type.lower():
                    eth_interfaces.append({"name": if_name, "type": if_type})

            logger.info(
                "Device %s (%s via %s) returned %d neighbors, %d interfaces",
                device.name, device.host, device.api_type,
                len(neighbors), len(eth_interfaces),
            )
            half_links = [
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
            return {"device_name": device.name, "neighbors": half_links, "interfaces": eth_interfaces}
        except Exception:
            logger.warning(
                "Discovery failed for %s (%s via %s)",
                device.name, device.host, device.api_type, exc_info=True,
            )
            return {"device_name": device.name, "neighbors": [], "interfaces": []}
        finally:
            await client.close()

    def _infer_hierarchy(
        self, all_half_links: list[dict[str, Any]],
    ) -> dict[str, str]:
        """Infer parent-child relationships from interface grouping.

        Groups neighbors by the local interface they're seen on.  Within each
        group containing multiple devices, the highest-scoring switch (by SFP
        port count) becomes the intermediate parent for all other devices in
        the group.  VPN tunnel neighbors are always direct children.

        Returns a dict mapping ``remote_identity -> inferred parent name``.
        """
        # Step 1 — pick ONE interface per remote device (prefer mgmt VLAN).
        device_if: dict[str, tuple[str, str, dict[str, Any]]] = {}
        for hl in all_half_links:
            remote_id = hl["remote_identity"]
            if not remote_id:
                continue
            iface = hl["local_interface"]
            querying_dev = hl["local_device"]

            existing = device_if.get(remote_id)
            if existing is None:
                device_if[remote_id] = (querying_dev, iface, hl)
            elif "mgmt" in iface.lower() and "mgmt" not in existing[1].lower():
                device_if[remote_id] = (querying_dev, iface, hl)

        # Step 2 — group by (querying_device, interface).
        groups: dict[tuple[str, str], list[tuple[str, dict[str, Any]]]] = {}
        for remote_id, (querying_dev, iface, hl) in device_if.items():
            key = (querying_dev, iface)
            groups.setdefault(key, []).append((remote_id, hl))

        # Step 3 — for each group, pick the best gateway switch.
        parent_map: dict[str, str] = {}
        for (querying_dev, iface), members in groups.items():
            # VPN tunnels → always direct children.
            if iface.startswith("<") or any(
                p in iface.lower() for p in _VPN_PATTERNS
            ):
                for remote_id, _ in members:
                    parent_map[remote_id] = querying_dev
                continue

            if len(members) <= 1:
                for remote_id, _ in members:
                    parent_map[remote_id] = querying_dev
                continue

            # Score each member for gateway potential.
            best_gw: str | None = None
            best_score = 0
            for remote_id, hl in members:
                score = _gateway_score(hl.get("remote_board", ""))
                if score > best_score:
                    best_score = score
                    best_gw = remote_id

            if best_gw and best_score > 0:
                for remote_id, _ in members:
                    if remote_id == best_gw:
                        parent_map[remote_id] = querying_dev
                    else:
                        parent_map.setdefault(remote_id, best_gw)
            else:
                # No switch found → all direct children.
                for remote_id, _ in members:
                    parent_map[remote_id] = querying_dev

        logger.info(
            "Hierarchy inference: %d devices mapped to parents",
            len(parent_map),
        )
        return parent_map

    def _auto_position(self, parent_name: str, index: int, total: int) -> Position:
        """Calculate tree position for a discovered device below its parent."""
        parent_pos = self._device_positions.get(parent_name, Position())
        offset_x = (index - (total - 1) / 2) * TREE_HORIZONTAL_SPACING
        return Position(
            x=round(parent_pos.x + offset_x),
            y=parent_pos.y + TREE_VERTICAL_SPACING,
        )

    def _recalculate_tree_positions(self) -> None:
        """Recalculate all discovered device positions as a hierarchical tree.

        Places children below their discovering parent, spread horizontally
        based on subtree width.  Configured devices keep their positions.
        """
        if not self.discovered_devices:
            return

        # Build parent → children mapping from discovered_by.
        children_of: dict[str, list[str]] = {}
        for dev in self.discovered_devices.values():
            children_of.setdefault(dev.discovered_by, []).append(dev.name)

        # Sort children alphabetically for consistent layout.
        for kids in children_of.values():
            kids.sort()

        # Calculate subtree leaf count for horizontal width allocation.
        def leaf_count(name: str) -> int:
            kids = children_of.get(name, [])
            if not kids:
                return 1
            return sum(leaf_count(k) for k in kids)

        # Recursively position children below their parent.
        def position_subtree(parent: str) -> None:
            kids = children_of.get(parent, [])
            if not kids:
                return

            parent_pos = self._device_positions.get(parent, Position())
            widths = [leaf_count(k) for k in kids]
            total_leaves = sum(widths)

            # Center children under parent.
            start_x = parent_pos.x - (total_leaves - 1) * TREE_HORIZONTAL_SPACING / 2
            cumulative = 0
            for kid, w in zip(kids, widths):
                kid_x = start_x + (cumulative + (w - 1) / 2) * TREE_HORIZONTAL_SPACING
                kid_pos = Position(
                    x=round(kid_x),
                    y=parent_pos.y + TREE_VERTICAL_SPACING,
                )
                if kid in self.discovered_devices:
                    self.discovered_devices[kid].position = kid_pos
                self._device_positions[kid] = kid_pos
                cumulative += w
                position_subtree(kid)

        # Start from roots (parents that aren't discovered devices themselves).
        for parent in list(children_of.keys()):
            if parent not in self.discovered_devices:
                position_subtree(parent)

        logger.info(
            "Tree layout: positioned %d discovered devices",
            len(self.discovered_devices),
        )

    async def _sweep(self) -> dict[str, Any]:
        """Query all devices, build topology, detect changes.

        Returns a dict with keys: added_devices, added_links, removed_links.
        """
        now = datetime.now(timezone.utc)

        # Collect all half-links and interface data from neighbor tables.
        tasks = [self._query_device(dev) for dev in self.devices]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        all_half_links: list[dict[str, Any]] = []
        for r in results:
            if isinstance(r, dict):
                all_half_links.extend(r.get("neighbors", []))
                # Build interface speed map from ethernet interface data.
                dev_name = r.get("device_name", "")
                iface_list = r.get("interfaces", [])
                if dev_name and iface_list:
                    for iface in iface_list:
                        if_name = iface.get("name") or iface.get("default-name", "")
                        if not if_name:
                            continue
                        # Try explicit speed field first (REST API returns this).
                        speed_str = iface.get("speed", "") or iface.get("rate", "")
                        speed_mbps = _parse_speed(speed_str)
                        # Fallback: parse max advertised speed (Classic API).
                        if speed_mbps == 0:
                            speed_mbps = _parse_advertise_speed(iface.get("advertise", ""))
                        # Fallback: infer from interface name.
                        if speed_mbps == 0:
                            speed_mbps = _infer_interface_speed(if_name)
                        if speed_mbps > 0:
                            self.interface_speeds.setdefault(dev_name, {})[if_name] = speed_mbps
            elif isinstance(r, Exception):
                logger.warning("Discovery sweep exception: %s", r)

        if not all_half_links:
            logger.debug("Discovery sweep: no neighbors found")
            return {"added_devices": [], "added_links": [], "removed_links": []}

        # Infer parent-child hierarchy from interface grouping.
        parent_map = self._infer_hierarchy(all_half_links)

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

            # Track potential new devices (skip blacklisted).
            if (
                remote_id not in self._configured_names
                and remote_id not in self.discovered_devices
                and hl.get("remote_address")
                and not (
                    self._visibility
                    and self._visibility.is_blacklisted_by_identity(
                        name=remote_id,
                        host=hl.get("remote_address", ""),
                        mac=hl.get("remote_mac", ""),
                    )
                )
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

            # Look up real interface speed from speed map.
            local_speed = self.interface_speeds.get(local_dev, {}).get(local_if, 0)
            remote_speed = self.interface_speeds.get(remote_id, {}).get(remote_if, 0) if remote_if != "auto" else 0
            link_speed = local_speed or remote_speed or 1000

            new_links[link_id] = DiscoveredLink(
                id=link_id,
                from_device=f"{local_dev}:{local_if}",
                to_device=f"{remote_id}:{remote_if}",
                speed=link_speed,
                type=link_type,
                confirmed=reverse_hl is not None,
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
            # Count new neighbors per inferred parent for positioning.
            parent_new_counts: dict[str, int] = {}
            for name, hl in new_device_candidates.items():
                parent = parent_map.get(name, hl["local_device"])
                parent_new_counts[parent] = parent_new_counts.get(parent, 0) + 1

            parent_indices: dict[str, int] = {}
            for name, hl in new_device_candidates.items():
                parent = parent_map.get(name, hl["local_device"])
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
                # Auto-add as queryable for next sweep if api_defaults has credentials.
                self.add_queryable_device(name, hl["remote_address"])
        else:
            # Even if not auto-adding, update last_seen on known discovered devices.
            for name in new_device_candidates:
                if name in self.discovered_devices:
                    self.discovered_devices[name].last_seen = now

        # Update discovered_by for existing devices based on hierarchy inference.
        hierarchy_changed = False
        for name, dev in self.discovered_devices.items():
            new_parent = parent_map.get(name)
            if new_parent and new_parent != dev.discovered_by:
                logger.info(
                    "Hierarchy update: %s parent %s → %s",
                    name, dev.discovered_by, new_parent,
                )
                dev.discovered_by = new_parent
                hierarchy_changed = True

        # Update link state.
        self.discovered_links = new_links

        # Build change report.
        added_links = [new_links[lid] for lid in added_link_ids]
        removed_links = list(removed_link_ids)

        logger.info(
            "Discovery sweep: %d half-links, %d full links (%d new, %d removed), "
            "%d new devices, %d queryable devices, %d devices with speed data",
            len(all_half_links),
            len(new_links),
            len(added_links),
            len(removed_links),
            len(added_devices),
            len(self.devices),
            len(self.interface_speeds),
        )

        # Recalculate tree layout if hierarchy changed or new devices were added.
        if added_devices or hierarchy_changed:
            self._recalculate_tree_positions()

        # Persist to disk.
        self._save_persistence()

        return {
            "added_devices": added_devices,
            "added_links": added_links,
            "removed_links": removed_links,
        }

    def remove_device(self, device_id: str) -> list[str]:
        """Remove a discovered device and its links. Returns removed link IDs."""
        removed_link_ids: list[str] = []
        self.discovered_devices.pop(device_id, None)
        self._device_positions.pop(device_id, None)
        self._configured_names.discard(device_id)

        # Also remove from queryable device list (cfg.devices shared reference).
        self._devices[:] = [d for d in self._devices if d.name != device_id]

        # Remove all links involving this device.
        for link_id in list(self.discovered_links.keys()):
            link = self.discovered_links[link_id]
            from_dev = link.from_device.split(":")[0]
            to_dev = link.to_device.split(":")[0]
            if device_id in (from_dev, to_dev):
                del self.discovered_links[link_id]
                removed_link_ids.append(link_id)

        self._save_persistence()
        logger.info(
            "Removed device %s and %d links", device_id, len(removed_link_ids),
        )
        return removed_link_ids

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
