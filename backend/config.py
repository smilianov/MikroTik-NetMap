"""YAML configuration loader with environment variable expansion."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml

from models import (
    DeviceConfig,
    LinkConfig,
    MapConfig,
    Position,
    ThresholdConfig,
)

_ENV_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")

# Default color thresholds matching the graduated ping system.
DEFAULT_THRESHOLDS: list[dict[str, Any]] = [
    {"max_seconds": 5, "color": "#22C55E", "label": "Online"},
    {"max_seconds": 10, "color": "#FFFF00", "label": "Degraded"},
    {"max_seconds": 15, "color": "#FFD700", "label": ""},
    {"max_seconds": 20, "color": "#FF8C00", "label": ""},
    {"max_seconds": 25, "color": "#FF6600", "label": ""},
    {"max_seconds": 30, "color": "#CC4400", "label": ""},
    {"max_seconds": 180, "color": "#EF4444", "label": "Down"},
]


def _expand_env(value: Any) -> Any:
    """Recursively expand ${VAR} references in strings."""
    if isinstance(value, str):
        return _ENV_RE.sub(lambda m: os.environ.get(m.group(1), ""), value)
    if isinstance(value, dict):
        return {k: _expand_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand_env(item) for item in value]
    return value


class NetMapConfig:
    """Parsed configuration for MikroTik-NetMap."""

    def __init__(self, config_path: str | Path) -> None:
        path = Path(config_path)
        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {path}")

        with open(path, encoding="utf-8") as f:
            raw = yaml.safe_load(f)

        data: dict[str, Any] = _expand_env(raw) or {}

        # Server settings.
        server = data.get("server", {})
        self.host: str = server.get("host", "0.0.0.0")
        self.port: int = server.get("port", 8585)
        self.cors_origins: list[str] = server.get("cors_origins", ["*"])

        # Ping settings.
        ping = data.get("ping", {})
        self.ping_interval: float = ping.get("interval", 2)
        self.ping_timeout: float = ping.get("timeout", 1)

        # API defaults (applied to devices that don't override, and to discovered devices).
        api_defaults = data.get("api_defaults", {})
        default_username = api_defaults.get("username", "admin")
        default_password = api_defaults.get("password", "")
        default_api_type = api_defaults.get("api_type", "rest")
        default_api_port = api_defaults.get("port", None)

        self.api_defaults: dict = {
            "username": default_username,
            "password": default_password,
            "api_type": default_api_type,
            "port": default_api_port,
        }

        # Color thresholds.
        raw_thresholds = data.get("thresholds", DEFAULT_THRESHOLDS)
        self.thresholds: list[ThresholdConfig] = [
            ThresholdConfig(**t) for t in raw_thresholds
        ]

        # Devices.
        self.devices: list[DeviceConfig] = []
        for d in data.get("devices", []):
            if "username" not in d:
                d["username"] = default_username
            if "api_type" not in d:
                d["api_type"] = default_api_type
            if "port" not in d and default_api_port:
                d["port"] = default_api_port
            if "position" in d and isinstance(d["position"], dict):
                d["position"] = Position(**d["position"])
            self.devices.append(DeviceConfig(**d))

        # Maps.
        raw_maps = data.get("maps", [{"name": "main", "label": "Network Overview"}])
        self.maps: list[MapConfig] = [MapConfig(**m) for m in raw_maps]

        # Links.
        self.links: list[LinkConfig] = [
            LinkConfig(**ln) for ln in data.get("links", [])
        ]

        # Discovery settings.
        discovery = data.get("discovery", {})
        self.discovery_enabled: bool = discovery.get("enabled", True)
        self.discovery_interval: int = discovery.get("interval", 300)
        self.discovery_auto_add_links: bool = discovery.get("auto_add_links", True)
        self.discovery_auto_add_devices: bool = discovery.get("auto_add_devices", False)
        self.discovery_protocols: list[str] = discovery.get("protocols", ["mndp", "lldp"])

        # Traffic monitor settings.
        traffic = data.get("traffic", {})
        self.traffic_enabled: bool = traffic.get("enabled", True)
        self.traffic_interval: int = traffic.get("interval", 10)
