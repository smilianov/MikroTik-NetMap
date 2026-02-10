"""MikroTik-NetMap — real-time network topology dashboard."""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from api.devices import router as devices_router, set_app_state
from api.websocket import ConnectionManager
from config import NetMapConfig
from models import PingState
from monitors.ping_monitor import PingMonitor

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

    # Share state with API routers.
    set_app_state(app_state)

    logger.info("MikroTik-NetMap started on %s:%d", cfg.host, cfg.port)
    yield

    # Shutdown.
    await ping.stop()
    logger.info("MikroTik-NetMap stopped")


app = FastAPI(
    title="MikroTik-NetMap",
    version="0.1.0",
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
    """Return thresholds and map definitions for the frontend."""
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
        "links": [
            {
                "from": ln.from_device,
                "to": ln.to_device,
                "speed": ln.speed,
                "type": ln.type.value,
            }
            for ln in cfg.links
        ],
    }


@app.get("/api/health")
async def health():
    """Health check endpoint."""
    cfg = app_state.get("config")
    ping = app_state.get("ping_monitor")
    return {
        "status": "ok",
        "devices": len(cfg.devices) if cfg else 0,
        "ws_clients": ws_manager.client_count,
        "ping_running": ping is not None and ping._running,
    }


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    """WebSocket endpoint for real-time ping state updates."""
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

    # Send config (thresholds, maps) so frontend knows how to render.
    cfg = app_state.get("config")
    if cfg:
        await ws.send_json({
            "type": "config",
            "thresholds": [
                {"max_seconds": t.max_seconds, "color": t.color, "label": t.label}
                for t in cfg.thresholds
            ],
            "devices": [
                {
                    "id": d.name,
                    "name": d.name,
                    "host": d.host,
                    "type": d.type.value,
                    "profile": d.profile,
                    "map": d.map,
                    "position": {"x": d.position.x, "y": d.position.y},
                }
                for d in cfg.devices
            ],
            "links": [
                {
                    "from": ln.from_device,
                    "to": ln.to_device,
                    "speed": ln.speed,
                    "type": ln.type.value,
                }
                for ln in cfg.links
            ],
        })

    try:
        while True:
            # Keep connection alive; handle client messages if needed.
            data = await ws.receive_text()
            # Future: handle client requests (device_detail, position updates)
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
