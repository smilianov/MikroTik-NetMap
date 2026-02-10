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

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from api.devices import router as devices_router, set_app_state
from api.websocket import ConnectionManager
from config import NetMapConfig
from models import DeviceConfig, DeviceType, PingState
from monitors.ping_monitor import PingMonitor
from monitors.topology_discovery import TopologyDiscovery
from monitors.traffic_monitor import TrafficMonitor

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


def _save_custom_positions(positions: dict[str, dict[str, float]]) -> None:
    """Save custom device positions to JSON file."""
    try:
        CUSTOM_POSITIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(CUSTOM_POSITIONS_FILE, "w", encoding="utf-8") as f:
            json.dump(positions, f, indent=2)
    except Exception:
        logger.warning("Failed to save custom positions", exc_info=True)


def _build_all_devices_list() -> list[dict[str, Any]]:
    """Build the combined device list (config + discovered) for WebSocket."""
    cfg = app_state.get("config")
    discovery = app_state.get("topology_discovery")
    custom_pos = app_state.get("custom_positions", {})
    if not cfg:
        return []

    devices = []
    for d in cfg.devices:
        pos = custom_pos.get(d.name, {"x": d.position.x, "y": d.position.y})
        devices.append({
            "id": d.name,
            "name": d.name,
            "host": d.host,
            "type": d.type.value,
            "profile": d.profile,
            "map": d.map,
            "position": pos,
        })

    if discovery:
        for dd in discovery.discovered_devices.values():
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
                "map": "main",
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
            })

    return links


def _infer_type_str(board: str, platform: str) -> str:
    """Infer device type string from board/platform."""
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

    # Add newly discovered devices to the ping monitor.
    ping = app_state.get("ping_monitor")
    if ping and added_devices:
        for dd in added_devices:
            dev_config = DeviceConfig(
                name=dd.name,
                host=dd.host,
                type=DeviceType(_infer_type_str(dd.board, dd.platform)),
                position=dd.position,
            )
            ping.add_device(dev_config)

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
                "map": "main",
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

    # Start ping monitor.
    ping = PingMonitor(
        devices=cfg.devices,
        interval=cfg.ping_interval,
        timeout=cfg.ping_timeout,
        on_update=_on_ping_update,
    )
    ping.start()
    app_state["ping_monitor"] = ping

    # Start topology discovery (if enabled and any device has credentials).
    discovery = None
    devices_with_creds = [d for d in cfg.devices if d.password]
    if cfg.discovery_enabled and devices_with_creds:
        discovery = TopologyDiscovery(
            devices=cfg.devices,
            interval=cfg.discovery_interval,
            auto_add_devices=cfg.discovery_auto_add_devices,
            auto_add_links=cfg.discovery_auto_add_links,
            on_update=_on_topology_update,
        )
        discovery.start()
        app_state["topology_discovery"] = discovery
        logger.info(
            "TopologyDiscovery enabled: %d devices with credentials, interval=%ds",
            len(devices_with_creds),
            cfg.discovery_interval,
        )
    else:
        if not cfg.discovery_enabled:
            logger.info("TopologyDiscovery disabled in config")
        elif not devices_with_creds:
            logger.info("TopologyDiscovery skipped: no devices have API credentials")

    # Load custom device positions (from drag-to-reposition).
    custom_positions = _load_custom_positions()
    app_state["custom_positions"] = custom_positions
    if custom_positions:
        logger.info("Loaded custom positions for %d devices", len(custom_positions))

    # Start traffic monitor (if enabled and any device has credentials).
    traffic = None
    if cfg.traffic_enabled and devices_with_creds:
        traffic = TrafficMonitor(
            devices=cfg.devices,
            interval=cfg.traffic_interval,
            on_update=_on_traffic_update,
        )
        traffic.start()
        app_state["traffic_monitor"] = traffic
        logger.info(
            "TrafficMonitor enabled: %d devices with credentials, interval=%ds",
            len(devices_with_creds),
            cfg.traffic_interval,
        )
    else:
        if not cfg.traffic_enabled:
            logger.info("TrafficMonitor disabled in config")
        elif not devices_with_creds:
            logger.info("TrafficMonitor skipped: no devices have API credentials")

    # Share state with API routers.
    set_app_state(app_state)

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
    version="0.3.0",
    lifespan=lifespan,
)

# CORS — allow frontend dev server.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# REST API.
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
        "maps": [
            {"name": m.name, "label": m.label, "parent": m.parent, "background": m.background}
            for m in cfg.maps
        ],
        "links": _build_all_links_list(),
    }


@app.get("/api/health")
async def health():
    """Health check endpoint."""
    cfg = app_state.get("config")
    ping = app_state.get("ping_monitor")
    discovery = app_state.get("topology_discovery")
    traffic = app_state.get("traffic_monitor")
    return {
        "status": "ok",
        "devices": len(cfg.devices) if cfg else 0,
        "ws_clients": ws_manager.client_count,
        "ping_running": ping is not None and ping._running,
        "discovery_running": discovery is not None and discovery._running,
        "traffic_running": traffic is not None and traffic._running,
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
    if cfg:
        await ws.send_json({
            "type": "config",
            "thresholds": [
                {"max_seconds": t.max_seconds, "color": t.color, "label": t.label}
                for t in cfg.thresholds
            ],
            "devices": _build_all_devices_list(),
            "links": _build_all_links_list(),
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
                        _save_custom_positions(custom_pos)

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
