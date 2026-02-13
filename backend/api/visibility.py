"""REST API routes for device visibility (hide / blacklist)."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/devices", tags=["visibility"])

# Reference to app state — set by main.py at startup.
_app_state: dict[str, Any] = {}


def set_app_state(state: dict[str, Any]) -> None:
    global _app_state
    _app_state = state


class BlacklistBody(BaseModel):
    reason: str = ""


async def _broadcast_visibility() -> None:
    """Broadcast current visibility state to all WebSocket clients."""
    vm = _app_state.get("visibility_manager")
    ws_mgr = _app_state.get("ws_manager")
    if not vm or not ws_mgr:
        return
    await ws_mgr.broadcast({
        "type": "visibility_update",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "hidden": vm.get_hidden_list(),
        "blacklisted": [d.id for d in vm.blacklisted.values()],
    })


def _find_device_info(device_id: str) -> dict[str, str]:
    """Look up host/mac for a device from config or discovered devices."""
    cfg = _app_state.get("config")
    discovery = _app_state.get("topology_discovery")
    host = ""
    mac = ""
    if cfg:
        for d in cfg.devices:
            if d.name == device_id:
                host = d.host
                break
    if discovery and device_id in discovery.discovered_devices:
        dd = discovery.discovered_devices[device_id]
        host = host or dd.host
        mac = dd.mac
    return {"host": host, "mac": mac}


# ── Fixed paths (must be defined BEFORE parameterised routes) ────

@router.get("/hidden")
async def list_hidden() -> list[str]:
    """Return list of hidden device IDs."""
    vm = _app_state.get("visibility_manager")
    if not vm:
        return []
    return vm.get_hidden_list()


@router.get("/blacklisted")
async def list_blacklisted() -> list[dict[str, Any]]:
    """Return list of blacklisted devices with metadata."""
    vm = _app_state.get("visibility_manager")
    if not vm:
        return []
    return vm.get_blacklisted_list()


# ── Parameterised routes ─────────────────────────────────────────

@router.post("/{device_id}/hide")
async def hide_device(device_id: str) -> dict[str, Any]:
    vm = _app_state.get("visibility_manager")
    if not vm:
        raise HTTPException(500, "Visibility manager not initialised")
    await vm.hide_device(device_id)
    await _broadcast_visibility()
    return {"ok": True, "device_id": device_id, "action": "hidden"}


@router.post("/{device_id}/unhide")
async def unhide_device(device_id: str) -> dict[str, Any]:
    vm = _app_state.get("visibility_manager")
    if not vm:
        raise HTTPException(500, "Visibility manager not initialised")
    await vm.unhide_device(device_id)
    await _broadcast_visibility()
    return {"ok": True, "device_id": device_id, "action": "unhidden"}


@router.post("/{device_id}/blacklist")
async def blacklist_device(device_id: str, body: BlacklistBody | None = None) -> dict[str, Any]:
    vm = _app_state.get("visibility_manager")
    if not vm:
        raise HTTPException(500, "Visibility manager not initialised")

    info = _find_device_info(device_id)
    reason = body.reason if body else ""

    await vm.blacklist_device(
        device_id=device_id,
        host=info["host"],
        mac=info["mac"],
        reason=reason,
    )

    # Remove from ping monitor.
    ping = _app_state.get("ping_monitor")
    if ping:
        ping.remove_device(device_id)

    # Remove from topology discovery.
    discovery = _app_state.get("topology_discovery")
    removed_links: list[str] = []
    if discovery:
        removed_links = discovery.remove_device(device_id)

    # Broadcast visibility + topology removal.
    await _broadcast_visibility()

    ws_mgr = _app_state.get("ws_manager")
    if ws_mgr:
        await ws_mgr.broadcast({
            "type": "topology_update",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "added_devices": [],
            "added_links": [],
            "removed_devices": [device_id],
            "removed_links": removed_links,
        })

    return {"ok": True, "device_id": device_id, "action": "blacklisted"}


@router.post("/{device_id}/unblacklist")
async def unblacklist_device(device_id: str) -> dict[str, Any]:
    vm = _app_state.get("visibility_manager")
    if not vm:
        raise HTTPException(500, "Visibility manager not initialised")

    await vm.unblacklist_device(device_id)
    await _broadcast_visibility()
    return {"ok": True, "device_id": device_id, "action": "unblacklisted"}
