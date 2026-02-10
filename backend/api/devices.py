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


@router.get("")
async def list_devices() -> list[dict[str, Any]]:
    """Return all devices with their current ping state."""
    config = _app_state.get("config")
    ping_monitor = _app_state.get("ping_monitor")
    if not config:
        return []

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
                "ping": {
                    "last_seen": state.last_seen.isoformat() if state and state.last_seen else None,
                    "rtt_ms": state.rtt_ms if state else None,
                    "is_alive": state.is_alive if state else False,
                },
            }

    raise HTTPException(404, f"Device '{device_id}' not found")
