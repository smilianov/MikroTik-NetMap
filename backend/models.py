"""Pydantic models for MikroTik-NetMap."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class DeviceType(str, Enum):
    ROUTER = "router"
    SWITCH = "switch"
    AP = "ap"
    SERVER = "server"
    OTHER = "other"


class LinkType(str, Enum):
    WIRED = "wired"
    WIRELESS = "wireless"
    VPN = "vpn"


class Position(BaseModel):
    x: float = 0.0
    y: float = 0.0


class DeviceConfig(BaseModel):
    """Device definition from config file."""

    name: str
    host: str
    type: DeviceType = DeviceType.ROUTER
    username: str = "admin"
    password: str = ""
    api_type: str = "rest"
    port: int | None = None
    profile: str = "edge"
    map: str = "main"
    position: Position = Field(default_factory=Position)


class LinkConfig(BaseModel):
    """Link definition from config file."""

    from_device: str = Field(alias="from")
    to_device: str = Field(alias="to")
    speed: int = 1000  # Mbps
    type: LinkType = LinkType.WIRED

    model_config = {"populate_by_name": True}


class MapConfig(BaseModel):
    """Map/submap definition."""

    name: str
    label: str = ""
    parent: str | None = None
    background: str | None = None


class ThresholdConfig(BaseModel):
    """Color threshold for ping status."""

    max_seconds: float
    color: str
    label: str = ""


class PingState(BaseModel):
    """Real-time ping state for a device."""

    device_id: str
    last_seen: datetime | None = None
    rtt_ms: float | None = None
    is_alive: bool = False


class InterfaceTraffic(BaseModel):
    """Traffic counters for a single interface on a device."""

    name: str
    rx_bps: float = 0.0
    tx_bps: float = 0.0
    running: bool = True


class DeviceDetail(BaseModel):
    """Extended device info from RouterOS API."""

    device_id: str
    model: str = ""
    ros_version: str = ""
    cpu_load: int = 0
    memory_used_pct: float = 0.0
    uptime: str = ""
    interfaces: list[dict[str, Any]] = Field(default_factory=list)


class DiscoveredDevice(BaseModel):
    """Device found via MNDP/LLDP neighbor discovery."""

    name: str
    host: str
    mac: str = ""
    platform: str = ""
    board: str = ""
    discovered_by: str  # which configured device found it
    discovered_on: str  # interface on the discovering device
    first_seen: datetime
    last_seen: datetime
    position: Position = Field(default_factory=Position)


class DiscoveredLink(BaseModel):
    """Link discovered from neighbor tables."""

    id: str  # "deviceA:if1-deviceB:if2"
    from_device: str = Field(alias="from")
    to_device: str = Field(alias="to")
    speed: int = 1000
    type: LinkType = LinkType.WIRED
    discovered: bool = True
    first_seen: datetime
    last_seen: datetime

    model_config = {"populate_by_name": True}


class WSMessage(BaseModel):
    """WebSocket message envelope."""

    type: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    data: Any = None
