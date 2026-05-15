"""REST API routes for device management."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/devices", tags=["devices"])

# Reference to app state — set by main.py at startup.
_app_state: dict[str, Any] = {}


def set_app_state(state: dict[str, Any]) -> None:
    global _app_state
    _app_state = state


def _endpoint_device(endpoint: str) -> str:
    return str(endpoint or "").split(":", 1)[0].strip()


def _configured_parent_map(config: Any) -> dict[str, str]:
    parents: dict[str, str] = {}
    for link in getattr(config, "links", []):
        parent = _endpoint_device(link.from_device)
        child = _endpoint_device(link.to_device)
        if parent and child and parent != child:
            parents.setdefault(child, parent)
    return parents


@router.get("")
async def list_devices() -> list[dict[str, Any]]:
    """Return all devices with their current ping state."""
    config = _app_state.get("config")
    ping_monitor = _app_state.get("ping_monitor")
    if not config:
        return []

    parent_map = _configured_parent_map(config)
    result = []
    for dev in config.devices:
        state = ping_monitor.states.get(dev.name) if ping_monitor else None
        result.append({
            "id": dev.name,
            "name": dev.name,
            "host": dev.host,
            "type": dev.type.value,
            "profile": dev.profile,
            "map": dev.map,
            "position": {"x": dev.position.x, "y": dev.position.y},
            "parent": parent_map.get(dev.name),
            "ping": {
                "last_seen": state.last_seen.isoformat() if state and state.last_seen else None,
                "rtt_ms": state.rtt_ms if state else None,
                "is_alive": state.is_alive if state else False,
            },
        })
    return result


@router.get("/{device_id}")
async def get_device(device_id: str) -> dict[str, Any]:
    """Return a single device with its ping state."""
    config = _app_state.get("config")
    ping_monitor = _app_state.get("ping_monitor")
    if not config:
        raise HTTPException(404, "No config loaded")

    parent_map = _configured_parent_map(config)
    for dev in config.devices:
        if dev.name == device_id:
            state = ping_monitor.states.get(dev.name) if ping_monitor else None
            return {
                "id": dev.name,
                "name": dev.name,
                "host": dev.host,
                "type": dev.type.value,
                "profile": dev.profile,
                "map": dev.map,
                "position": {"x": dev.position.x, "y": dev.position.y},
                "parent": parent_map.get(dev.name),
                "ping": {
                    "last_seen": state.last_seen.isoformat() if state and state.last_seen else None,
                    "rtt_ms": state.rtt_ms if state else None,
                    "is_alive": state.is_alive if state else False,
                },
            }

    raise HTTPException(404, f"Device '{device_id}' not found")
