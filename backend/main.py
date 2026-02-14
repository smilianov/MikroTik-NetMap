"""MikroTik-NetMap — real-time network topology dashboard."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from api.devices import router as devices_router, set_app_state
from api.links import router as links_router, set_app_state as set_links_state
from api.visibility import router as visibility_router, set_app_state as set_visibility_state
from api.websocket import ConnectionManager
from config import NetMapConfig
from manual_link_manager import ManualLinkManager
from models import DeviceConfig, DeviceType, PingState
from pydantic import BaseModel as _BaseModel
from monitors.ping_monitor import PingMonitor
from monitors.topology_discovery import TopologyDiscovery, _infer_device_type
from monitors.traffic_monitor import TrafficMonitor
from visibility_manager import VisibilityManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
)
logger = logging.getLogger("netmap")

# Resolve config path: env var > ./config/netmap.yaml > ../config/netmap.yaml
CONFIG_PATH = os.environ.get(
    "NETMAP_CONFIG",
    str(Path(__file__).resolve().parent.parent / "config" / "netmap.yaml"),
)

ws_manager = ConnectionManager()
app_state: dict = {}

# Custom device positions file (drag-to-reposition persistence).
CUSTOM_POSITIONS_FILE = (
    Path(__file__).resolve().parent.parent / "config" / "custom_positions.json"
)


def _load_custom_positions() -> dict[str, dict[str, float]]:
    """Load custom device positions from JSON file."""
    if not CUSTOM_POSITIONS_FILE.exists():
        return {}
    try:
        with open(CUSTOM_POSITIONS_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        logger.warning("Failed to load custom positions", exc_info=True)
        return {}


async def _save_custom_positions(positions: dict[str, dict[str, float]]) -> None:
    """Save custom device positions to JSON file (async to avoid blocking event loop)."""
    def _write() -> None:
        CUSTOM_POSITIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(CUSTOM_POSITIONS_FILE, "w", encoding="utf-8") as f:
            json.dump(positions, f, indent=2)
    try:
        await asyncio.to_thread(_write)
    except Exception:
        logger.warning("Failed to save custom positions", exc_info=True)


# Device-to-map overrides (persisted across restarts).
DEVICE_MAPS_FILE = (
    Path(__file__).resolve().parent.parent / "config" / "device_maps.json"
)


def _load_device_maps() -> dict[str, str]:
    """Load device-to-map overrides from JSON file."""
    if not DEVICE_MAPS_FILE.exists():
        return {}
    try:
        with open(DEVICE_MAPS_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        logger.warning("Failed to load device maps", exc_info=True)
        return {}


async def _save_device_maps(maps: dict[str, str]) -> None:
    """Save device-to-map overrides to JSON file."""
    def _write() -> None:
        DEVICE_MAPS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(DEVICE_MAPS_FILE, "w", encoding="utf-8") as f:
            json.dump(maps, f, indent=2)
    try:
        await asyncio.to_thread(_write)
    except Exception:
        logger.warning("Failed to save device maps", exc_info=True)


# Map label overrides (persisted across restarts).
MAP_LABELS_FILE = (
    Path(__file__).resolve().parent.parent / "config" / "map_labels.json"
)


def _load_map_labels() -> dict[str, str]:
    """Load map label overrides from JSON file."""
    if not MAP_LABELS_FILE.exists():
        return {}
    try:
        with open(MAP_LABELS_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        logger.warning("Failed to load map labels", exc_info=True)
        return {}


async def _save_map_labels(labels: dict[str, str]) -> None:
    """Save map label overrides to JSON file."""
    def _write() -> None:
        MAP_LABELS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(MAP_LABELS_FILE, "w", encoding="utf-8") as f:
            json.dump(labels, f, indent=2)
    try:
        await asyncio.to_thread(_write)
    except Exception:
        logger.warning("Failed to save map labels", exc_info=True)


# Custom maps (created from UI, persisted across restarts).
CUSTOM_MAPS_FILE = (
    Path(__file__).resolve().parent.parent / "config" / "custom_maps.json"
)


def _load_custom_maps() -> list[dict[str, str]]:
    """Load custom maps from JSON file."""
    if not CUSTOM_MAPS_FILE.exists():
        return []
    try:
        with open(CUSTOM_MAPS_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        logger.warning("Failed to load custom maps", exc_info=True)
        return []


async def _save_custom_maps(maps: list[dict[str, str]]) -> None:
    """Save custom maps to JSON file."""
    def _write() -> None:
        CUSTOM_MAPS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(CUSTOM_MAPS_FILE, "w", encoding="utf-8") as f:
            json.dump(maps, f, indent=2)
    try:
        await asyncio.to_thread(_write)
    except Exception:
        logger.warning("Failed to save custom maps", exc_info=True)


def _get_maps_list() -> list[dict[str, Any]]:
    """Build the maps list: config maps + custom maps, with label overrides."""
    cfg = app_state.get("config")
    if not cfg:
        return []
    map_labels = app_state.get("map_labels", {})
    result = [
        {
            "name": m.name,
            "label": map_labels.get(m.name, m.label),
            "parent": m.parent,
            "background": m.background,
        }
        for m in cfg.maps
    ]
    # Append custom maps (user-created from UI).
    for cm in app_state.get("custom_maps", []):
        name = cm["name"]
        result.append({
            "name": name,
            "label": map_labels.get(name, cm.get("label", name)),
            "parent": None,
            "background": None,
        })
    return result


def _get_all_map_names() -> set[str]:
    """Get all valid map names (config + custom)."""
    cfg = app_state.get("config")
    names = {m.name for m in cfg.maps} if cfg else set()
    for cm in app_state.get("custom_maps", []):
        names.add(cm["name"])
    return names


def _build_all_devices_list() -> list[dict[str, Any]]:
    """Build the combined device list (config + discovered) for WebSocket."""
    cfg = app_state.get("config")
    discovery = app_state.get("topology_discovery")
    custom_pos = app_state.get("custom_positions", {})
    device_maps = app_state.get("device_maps", {})
    visibility = app_state.get("visibility_manager")
    if not cfg:
        return []

    devices = []
    for d in cfg.devices:
        if visibility and visibility.is_blacklisted(d.name):
            continue
        pos = custom_pos.get(d.name, {"x": d.position.x, "y": d.position.y})
        devices.append({
            "id": d.name,
            "name": d.name,
            "host": d.host,
            "type": d.type.value,
            "profile": d.profile,
            "map": device_maps.get(d.name, d.map),
            "position": pos,
        })

    if discovery:
        for dd in discovery.discovered_devices.values():
            if visibility and visibility.is_blacklisted(dd.name):
                continue
            # Don't duplicate devices already in config.
            if any(d["id"] == dd.name for d in devices):
                continue
            pos = custom_pos.get(dd.name, {"x": dd.position.x, "y": dd.position.y})
            devices.append({
                "id": dd.name,
                "name": dd.name,
                "host": dd.host,
                "type": _infer_type_str(dd.board, dd.platform),
                "profile": "edge",
                "map": device_maps.get(dd.name, "main"),
                "position": pos,
                "discovered": True,
            })

    return devices


def _build_all_links_list() -> list[dict[str, Any]]:
    """Build the combined link list (config + discovered) for WebSocket."""
    cfg = app_state.get("config")
    discovery = app_state.get("topology_discovery")
    if not cfg:
        return []

    links = [
        {
            "from": ln.from_device,
            "to": ln.to_device,
            "speed": ln.speed,
            "type": ln.type.value,
        }
        for ln in cfg.links
    ]

    if discovery:
        for dl in discovery.discovered_links.values():
            links.append({
                "from": dl.from_device,
                "to": dl.to_device,
                "speed": dl.speed,
                "type": dl.type.value,
                "discovered": True,
                "confirmed": dl.confirmed,
            })

    # Include manual links.
    manual_mgr = app_state.get("manual_link_manager")
    if manual_mgr:
        for ml in manual_mgr.get_all():
            links.append({
                "from": ml["from"],
                "to": ml["to"],
                "speed": ml.get("speed", 1000),
                "type": ml.get("type", "wired"),
                "manual": True,
            })

    return links


def _infer_type_str(board: str, platform: str) -> str:
    """Infer device type string from board/platform (delegates to topology_discovery)."""
    return _infer_device_type(board, platform)


async def _on_ping_update(states: list[PingState]) -> None:
    """Called by PingMonitor after every sweep — broadcasts to WebSocket clients."""
    await ws_manager.broadcast({
        "type": "ping_state",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "devices": [
            {
                "id": s.device_id,
                "last_seen": s.last_seen.isoformat() if s.last_seen else None,
                "rtt_ms": s.rtt_ms,
                "is_alive": s.is_alive,
            }
            for s in states
        ],
    })


async def _on_topology_update(changes: dict[str, Any]) -> None:
    """Called by TopologyDiscovery when topology changes are detected."""
    added_devices = changes.get("added_devices", [])
    added_links = changes.get("added_links", [])
    removed_links = changes.get("removed_links", [])

    cfg = app_state.get("config")
    api_defaults = cfg.api_defaults if cfg else {}

    # Add newly discovered devices to the ping monitor and traffic monitor.
    ping = app_state.get("ping_monitor")
    traffic = app_state.get("traffic_monitor")
    for dd in added_devices:
        dev_config = DeviceConfig(
            name=dd.name,
            host=dd.host,
            type=DeviceType(_infer_type_str(dd.board, dd.platform)),
            position=dd.position,
        )
        if ping:
            ping.add_device(dev_config)

        # Also add to traffic monitor if api_defaults has credentials.
        if traffic and api_defaults.get("password"):
            traffic_config = DeviceConfig(
                name=dd.name,
                host=dd.host,
                username=api_defaults.get("username", "admin"),
                password=api_defaults["password"],
                api_type=api_defaults.get("api_type", "rest"),
                port=api_defaults.get("port"),
            )
            traffic.add_device(traffic_config)

    # Broadcast topology update to all WebSocket clients.
    await ws_manager.broadcast({
        "type": "topology_update",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "added_devices": [
            {
                "id": dd.name,
                "name": dd.name,
                "host": dd.host,
                "type": _infer_type_str(dd.board, dd.platform),
                "profile": "edge",
                "map": app_state.get("device_maps", {}).get(dd.name, "main"),
                "position": {"x": dd.position.x, "y": dd.position.y},
                "discovered": True,
            }
            for dd in added_devices
        ],
        "added_links": [
            {
                "from": dl.from_device,
                "to": dl.to_device,
                "speed": dl.speed,
                "type": dl.type.value,
                "discovered": True,
                "confirmed": dl.confirmed,
            }
            for dl in added_links
        ],
        "removed_links": removed_links,
    })


async def _on_traffic_update(
    traffic_data: dict[str, dict[str, dict[str, Any]]],
) -> None:
    """Called by TrafficMonitor after every sweep — broadcasts to WebSocket clients."""
    await ws_manager.broadcast({
        "type": "traffic_state",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "interfaces": traffic_data,
    })


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Start background monitors on app startup, stop on shutdown."""
    # Load config.
    logger.info("Loading config from %s", CONFIG_PATH)
    cfg = NetMapConfig(CONFIG_PATH)
    app_state["config"] = cfg

    logger.info(
        "Loaded %d devices, %d maps, %d links, %d thresholds",
        len(cfg.devices),
        len(cfg.maps),
        len(cfg.links),
        len(cfg.thresholds),
    )

    # Load visibility state (hidden / blacklisted devices).
    visibility = VisibilityManager()
    app_state["visibility_manager"] = visibility

    # Load manual links.
    manual_links = ManualLinkManager()
    app_state["manual_link_manager"] = manual_links

    # Start ping monitor.
    ping = PingMonitor(
        devices=cfg.devices,
        interval=cfg.ping_interval,
        timeout=cfg.ping_timeout,
        on_update=_on_ping_update,
    )
    ping.start()
    app_state["ping_monitor"] = ping

    # Start topology discovery (if enabled and any device has credentials or api_defaults has password).
    discovery = None
    devices_with_creds = [d for d in cfg.devices if d.password or d.ssh_key_file]
    has_default_creds = bool(cfg.api_defaults.get("password"))
    if cfg.discovery_enabled and (devices_with_creds or has_default_creds):
        discovery = TopologyDiscovery(
            devices=cfg.devices,
            interval=cfg.discovery_interval,
            auto_add_devices=cfg.discovery_auto_add_devices,
            auto_add_links=cfg.discovery_auto_add_links,
            on_update=_on_topology_update,
            visibility_manager=visibility,
            api_defaults=cfg.api_defaults,
        )
        discovery.start()
        app_state["topology_discovery"] = discovery
        logger.info(
            "TopologyDiscovery enabled: %d devices with credentials, "
            "api_defaults password=%s, interval=%ds",
            len(devices_with_creds),
            "yes" if has_default_creds else "no",
            cfg.discovery_interval,
        )

        # Seed PingMonitor with previously discovered devices (persisted across restarts).
        if discovery.discovered_devices:
            seeded = 0
            for dd in discovery.discovered_devices.values():
                if visibility.is_blacklisted(dd.name):
                    continue
                dev_config = DeviceConfig(
                    name=dd.name,
                    host=dd.host,
                    type=DeviceType(_infer_type_str(dd.board, dd.platform)),
                    position=dd.position,
                )
                ping.add_device(dev_config)
                seeded += 1
            logger.info(
                "Seeded PingMonitor with %d persisted discovered devices",
                seeded,
            )
    else:
        if not cfg.discovery_enabled:
            logger.info("TopologyDiscovery disabled in config")
        elif not devices_with_creds and not has_default_creds:
            logger.info("TopologyDiscovery skipped: no devices have API credentials")

    # Load custom device positions (from drag-to-reposition).
    custom_positions = _load_custom_positions()
    app_state["custom_positions"] = custom_positions
    if custom_positions:
        logger.info("Loaded custom positions for %d devices", len(custom_positions))

    # Load device-to-map overrides.
    device_maps = _load_device_maps()
    app_state["device_maps"] = device_maps
    if device_maps:
        logger.info("Loaded map overrides for %d devices", len(device_maps))

    # Load map label overrides.
    map_labels = _load_map_labels()
    app_state["map_labels"] = map_labels
    if map_labels:
        logger.info("Loaded label overrides for %d maps", len(map_labels))

    # Load custom maps (created from UI).
    custom_maps = _load_custom_maps()
    app_state["custom_maps"] = custom_maps
    if custom_maps:
        logger.info("Loaded %d custom maps", len(custom_maps))

    # Start traffic monitor (if enabled and any device has credentials or api_defaults has password).
    traffic = None
    if cfg.traffic_enabled and (devices_with_creds or has_default_creds):
        traffic = TrafficMonitor(
            devices=cfg.devices,
            interval=cfg.traffic_interval,
            on_update=_on_traffic_update,
            api_defaults=cfg.api_defaults,
        )
        # Seed with persisted discovered devices that have api_defaults credentials.
        if discovery and discovery.discovered_devices and has_default_creds:
            for dd in discovery.discovered_devices.values():
                if visibility.is_blacklisted(dd.name):
                    continue
                traffic_dev = DeviceConfig(
                    name=dd.name,
                    host=dd.host,
                    username=cfg.api_defaults.get("username", "admin"),
                    password=cfg.api_defaults["password"],
                    api_type=cfg.api_defaults.get("api_type", "rest"),
                    port=cfg.api_defaults.get("port"),
                )
                traffic.add_device(traffic_dev)
        traffic.start()
        app_state["traffic_monitor"] = traffic
        logger.info(
            "TrafficMonitor enabled: %d devices with credentials, interval=%ds",
            len(traffic.devices),
            cfg.traffic_interval,
        )
    else:
        if not cfg.traffic_enabled:
            logger.info("TrafficMonitor disabled in config")
        elif not devices_with_creds and not has_default_creds:
            logger.info("TrafficMonitor skipped: no devices have API credentials")

    # Share state with API routers.
    app_state["ws_manager"] = ws_manager
    set_app_state(app_state)
    set_visibility_state(app_state)
    set_links_state(app_state)

    logger.info("MikroTik-NetMap started on %s:%d", cfg.host, cfg.port)
    yield

    # Shutdown.
    if traffic:
        await traffic.stop()
    if discovery:
        await discovery.stop()
    await ping.stop()
    logger.info("MikroTik-NetMap stopped")


app = FastAPI(
    title="MikroTik-NetMap",
    version="0.4.0-beta",
    lifespan=lifespan,
)

# CORS — allow frontend dev server.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# REST API (visibility and links first — fixed paths must match before /{device_id}).
app.include_router(visibility_router)
app.include_router(links_router)
app.include_router(devices_router)


@app.get("/api/config")
async def get_config():
    """Return thresholds, maps, devices, and links (including discovered)."""
    cfg = app_state.get("config")
    if not cfg:
        return {}
    return {
        "thresholds": [
            {"max_seconds": t.max_seconds, "color": t.color, "label": t.label}
            for t in cfg.thresholds
        ],
        "maps": _get_maps_list(),
        "links": _build_all_links_list(),
    }


class _SetMapBody(_BaseModel):
    map: str


@app.put("/api/devices/{device_id}/map")
async def set_device_map(device_id: str, body: _SetMapBody):
    """Change a device's map assignment."""
    cfg = app_state.get("config")
    if not cfg:
        raise HTTPException(status_code=500, detail="Config not loaded")

    valid_maps = _get_all_map_names()
    if body.map not in valid_maps:
        raise HTTPException(status_code=400, detail=f"Unknown map: {body.map}")

    device_maps = app_state.get("device_maps", {})
    device_maps[device_id] = body.map
    app_state["device_maps"] = device_maps
    await _save_device_maps(device_maps)

    await ws_manager.broadcast({
        "type": "device_map_change",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "device_id": device_id,
        "map": body.map,
    })

    return {"ok": True, "device_id": device_id, "map": body.map}


class _RenameMapBody(_BaseModel):
    label: str


@app.put("/api/maps/{map_name}/label")
async def rename_map(map_name: str, body: _RenameMapBody):
    """Rename a map's display label."""
    cfg = app_state.get("config")
    if not cfg:
        raise HTTPException(status_code=500, detail="Config not loaded")

    valid_maps = _get_all_map_names()
    if map_name not in valid_maps:
        raise HTTPException(status_code=400, detail=f"Unknown map: {map_name}")

    label = body.label.strip()
    if not label:
        raise HTTPException(status_code=400, detail="Label cannot be empty")

    map_labels = app_state.get("map_labels", {})
    map_labels[map_name] = label
    app_state["map_labels"] = map_labels
    await _save_map_labels(map_labels)

    await ws_manager.broadcast({
        "type": "map_label_change",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "map_name": map_name,
        "label": label,
    })

    return {"ok": True, "map_name": map_name, "label": label}


class _CreateMapBody(_BaseModel):
    name: str
    label: str = ""


@app.post("/api/maps")
async def create_map(body: _CreateMapBody):
    """Create a new map."""
    name = body.name.strip().lower().replace(" ", "-")
    if not name:
        raise HTTPException(status_code=400, detail="Map name cannot be empty")

    existing = _get_all_map_names()
    if name in existing:
        raise HTTPException(status_code=400, detail=f"Map already exists: {name}")

    label = body.label.strip() or name
    custom_maps = app_state.get("custom_maps", [])
    custom_maps.append({"name": name, "label": label})
    app_state["custom_maps"] = custom_maps
    await _save_custom_maps(custom_maps)

    await ws_manager.broadcast({
        "type": "maps_changed",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "maps": _get_maps_list(),
    })

    return {"ok": True, "name": name, "label": label}


@app.delete("/api/maps/{map_name}")
async def delete_map(map_name: str):
    """Delete a custom map (moves devices back to main)."""
    custom_maps = app_state.get("custom_maps", [])
    names = {cm["name"] for cm in custom_maps}
    if map_name not in names:
        raise HTTPException(status_code=400, detail="Can only delete custom maps")

    custom_maps = [cm for cm in custom_maps if cm["name"] != map_name]
    app_state["custom_maps"] = custom_maps
    await _save_custom_maps(custom_maps)

    # Move any devices on this map back to main.
    device_maps = app_state.get("device_maps", {})
    moved = []
    for dev_id, m in list(device_maps.items()):
        if m == map_name:
            device_maps[dev_id] = "main"
            moved.append(dev_id)
    if moved:
        app_state["device_maps"] = device_maps
        await _save_device_maps(device_maps)

    await ws_manager.broadcast({
        "type": "maps_changed",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "maps": _get_maps_list(),
    })

    return {"ok": True, "deleted": map_name, "devices_moved_to_main": moved}


@app.get("/api/health")
async def health():
    """Health check endpoint."""
    cfg = app_state.get("config")
    ping = app_state.get("ping_monitor")
    discovery = app_state.get("topology_discovery")
    traffic = app_state.get("traffic_monitor")
    return {
        "status": "ok",
        "version": "0.4.0-beta",
        "devices": len(cfg.devices) if cfg else 0,
        "ws_clients": ws_manager.client_count,
        "ping_running": ping is not None and getattr(ping, "_running", False),
        "discovery_running": discovery is not None and getattr(discovery, "_running", False),
        "traffic_running": traffic is not None and getattr(traffic, "_running", False),
        "discovered_devices": len(discovery.discovered_devices) if discovery else 0,
        "discovered_links": len(discovery.discovered_links) if discovery else 0,
    }


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    """WebSocket endpoint for real-time state updates."""
    await ws_manager.connect(ws)

    # Send initial full state on connect.
    ping = app_state.get("ping_monitor")
    if ping:
        await ws.send_json({
            "type": "ping_state",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "devices": [
                {
                    "id": s.device_id,
                    "last_seen": s.last_seen.isoformat() if s.last_seen else None,
                    "rtt_ms": s.rtt_ms,
                    "is_alive": s.is_alive,
                }
                for s in ping.states.values()
            ],
        })

    # Send config (thresholds, maps, devices, links — including discovered).
    cfg = app_state.get("config")
    visibility = app_state.get("visibility_manager")
    if cfg:
        await ws.send_json({
            "type": "config",
            "thresholds": [
                {"max_seconds": t.max_seconds, "color": t.color, "label": t.label}
                for t in cfg.thresholds
            ],
            "maps": _get_maps_list(),
            "devices": _build_all_devices_list(),
            "links": _build_all_links_list(),
            "hidden": visibility.get_hidden_list() if visibility else [],
            "blacklisted": [d.id for d in visibility.blacklisted.values()] if visibility else [],
        })

    # Send latest traffic state if available.
    traffic_mon = app_state.get("traffic_monitor")
    if traffic_mon and traffic_mon.latest_traffic:
        await ws.send_json({
            "type": "traffic_state",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "interfaces": traffic_mon.latest_traffic,
        })

    try:
        while True:
            data = await ws.receive_text()
            try:
                msg = json.loads(data)
                msg_type = msg.get("type")

                if msg_type == "position_update":
                    device_id = msg.get("device_id")
                    position = msg.get("position")
                    if device_id and position:
                        # Persist to custom positions file.
                        custom_pos = app_state.get("custom_positions", {})
                        custom_pos[device_id] = {
                            "x": float(position["x"]),
                            "y": float(position["y"]),
                        }
                        app_state["custom_positions"] = custom_pos
                        await _save_custom_positions(custom_pos)

                        # Broadcast to all clients.
                        await ws_manager.broadcast({
                            "type": "position_update",
                            "device_id": device_id,
                            "position": custom_pos[device_id],
                        })
            except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                logger.debug("Invalid WebSocket message: %s", data[:200])
    except WebSocketDisconnect:
        pass
    finally:
        await ws_manager.disconnect(ws)


# Serve frontend static files (built React app) if the dist directory exists.
_frontend_dist = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if _frontend_dist.exists():
    app.mount("/", StaticFiles(directory=str(_frontend_dist), html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn

    cfg = NetMapConfig(CONFIG_PATH)
    uvicorn.run(
        "main:app",
        host=cfg.host,
        port=cfg.port,
        reload=True,
        reload_dirs=[str(Path(__file__).parent)],
    )
