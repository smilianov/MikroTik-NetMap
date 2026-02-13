"""REST API routes for manual link management."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/links", tags=["links"])

# Reference to app state — set by main.py at startup.
_app_state: dict[str, Any] = {}


def set_app_state(state: dict[str, Any]) -> None:
    global _app_state
    _app_state = state


class CreateLinkBody(BaseModel):
    from_device: str  # "deviceA:interface"
    to_device: str  # "deviceB:interface"
    speed: int = 1000
    type: str = "wired"


class UpdateLinkBody(BaseModel):
    from_device: str | None = None
    to_device: str | None = None
    speed: int | None = None
    type: str | None = None


async def _broadcast_link_change(
    added: list[dict] | None = None,
    removed: list[str] | None = None,
) -> None:
    """Broadcast link changes to all WebSocket clients."""
    ws_mgr = _app_state.get("ws_manager")
    if not ws_mgr:
        return
    await ws_mgr.broadcast({
        "type": "topology_update",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "added_devices": [],
        "added_links": added or [],
        "removed_links": removed or [],
    })


@router.get("/manual")
async def list_manual_links():
    """List all manually created links."""
    mgr = _app_state.get("manual_link_manager")
    if not mgr:
        return []
    return mgr.get_all()


@router.post("")
async def create_link(body: CreateLinkBody):
    """Create a manual link between two devices."""
    mgr = _app_state.get("manual_link_manager")
    if not mgr:
        raise HTTPException(status_code=500, detail="Manual link manager not available")

    link = await mgr.create_link(
        from_device=body.from_device,
        to_device=body.to_device,
        speed=body.speed,
        link_type=body.type,
    )

    # Broadcast the new link.
    await _broadcast_link_change(added=[{
        "from": link["from"],
        "to": link["to"],
        "speed": link["speed"],
        "type": link["type"],
        "manual": True,
    }])

    return link


@router.put("/{link_id:path}")
async def update_link(link_id: str, body: UpdateLinkBody):
    """Update a manual link."""
    mgr = _app_state.get("manual_link_manager")
    if not mgr:
        raise HTTPException(status_code=500, detail="Manual link manager not available")

    updates: dict[str, Any] = {}
    if body.from_device is not None:
        updates["from"] = body.from_device
    if body.to_device is not None:
        updates["to"] = body.to_device
    if body.speed is not None:
        updates["speed"] = body.speed
    if body.type is not None:
        updates["type"] = body.type

    result = await mgr.update_link(link_id, updates)
    if not result:
        raise HTTPException(status_code=404, detail="Link not found")

    # Broadcast: remove old, add updated.
    await _broadcast_link_change(
        removed=[link_id],
        added=[{
            "from": result["from"],
            "to": result["to"],
            "speed": result["speed"],
            "type": result["type"],
            "manual": True,
        }],
    )

    return result


@router.delete("/{link_id:path}")
async def delete_link(link_id: str):
    """Delete a manual link."""
    mgr = _app_state.get("manual_link_manager")
    if not mgr:
        raise HTTPException(status_code=500, detail="Manual link manager not available")

    deleted = await mgr.delete_link(link_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Link not found")

    # Broadcast removal.
    await _broadcast_link_change(removed=[link_id])

    return {"status": "ok"}
