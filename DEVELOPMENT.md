# Development Guide

## Prerequisites

| Tool | Version | Install |
|------|---------|---------|
| Python | 3.13+ | `brew install python` |
| Node.js | 22+ | `brew install node` |
| Git | any | `brew install git` |
| Docker | 27+ | [Docker Desktop](https://www.docker.com/products/docker-desktop/) (optional) |

---

## Initial Setup

### 1. Clone the repository

```bash
git clone git@github.com:smilianov/MikroTik-NetMap.git
cd MikroTik-NetMap
```

### 2. Backend setup

```bash
# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r backend/requirements.txt

# Copy config
cp config/netmap.example.yaml config/netmap.yaml
cp .env.example .env
```

### 3. Frontend setup

```bash
cd frontend
npm install
cd ..
```

### 4. Configure devices

Edit `config/netmap.yaml` — add your MikroTik devices:

```yaml
devices:
  - name: my-router
    host: 192.168.1.1
    type: router
    profile: edge
    password: "${MY_ROUTER_PASS}"
    map: main
    position: {x: 400, y: 200}
```

Set passwords in `.env`:
```
MY_ROUTER_PASS=your-actual-password
```

---

## Running in Development

### Start backend (Terminal 1)

```bash
source .venv/bin/activate
cd backend
python -m uvicorn main:app --host 0.0.0.0 --port 8585 --reload
```

The `--reload` flag enables hot-reload: changes to Python files restart the server automatically.

### Start frontend (Terminal 2)

```bash
cd frontend
npm run dev
```

Vite dev server starts on **http://localhost:5173** and proxies API/WebSocket requests to the backend on port 8585.

### Verify it works

1. Open http://localhost:5173
2. You should see the dark dashboard with device nodes on the map
3. The status bar should show "LIVE" in green
4. Devices that respond to ping will appear green; unreachable ones cycle through yellow → orange → red

---

## Project Layout

### Backend (`backend/`)

```
backend/
├── main.py              # FastAPI app, lifespan, routes, WebSocket
├── config.py            # YAML loader with ${ENV} expansion
├── models.py            # Pydantic models (DeviceConfig, PingState, etc.)
├── requirements.txt     # Python dependencies
├── monitors/
│   ├── __init__.py
│   ├── ping_monitor.py          # Async ICMP ping loop (icmplib)
│   └── topology_discovery.py    # MNDP/LLDP neighbour discovery
├── api/
│   ├── __init__.py
│   ├── websocket.py     # ConnectionManager — broadcast to all clients
│   └── devices.py       # GET /api/devices endpoints
└── mikrotik/
    ├── __init__.py
    └── client.py         # RouterOS API client (REST + Classic)
```

**Key patterns:**
- FastAPI lifespan context starts/stops PingMonitor and TopologyDiscovery
- PingMonitor runs as an `asyncio.Task` calling `async_ping` every 2 seconds
- TopologyDiscovery runs as an `asyncio.Task` querying `/ip/neighbor` every 5 minutes
- `create_client()` factory picks REST (httpx) or Classic (routeros_api) based on `api_type`
- WebSocket broadcasts are fire-and-forget; dead connections are cleaned up automatically
- Config supports `${ENV_VAR}` syntax for secrets (never commit passwords)

### Frontend (`frontend/`)

```
frontend/src/
├── App.tsx              # Root layout: StatusBar + Sidebar + Map + Panel
├── main.tsx             # React entry point
├── index.css            # Global styles, vis-network tooltip theme
├── components/
│   ├── NetworkMap.tsx    # vis-network canvas with colour animation loop
│   ├── StatusBar.tsx     # Top bar with device counts
│   ├── Sidebar.tsx       # Searchable device list
│   └── DevicePanel.tsx   # Slide-in detail panel (double-click)
├── hooks/
│   └── useWebSocket.ts   # WebSocket connection with auto-reconnect
├── stores/
│   └── networkStore.ts   # Zustand store for all state
└── utils/
    ├── colorThresholds.ts # Graduated colour computation from timestamp
    ├── deviceIcons.ts     # SVG device icon generator with status dots
    └── formatters.ts      # Duration, bandwidth, RTT formatting
```

**Key patterns:**
- `useWebSocket` connects on mount, auto-reconnects on disconnect
- `networkStore` (Zustand) holds all state — devices, ping data, thresholds, UI state
- `NetworkMap` runs a ~10 fps animation loop (`requestAnimationFrame`) that recomputes node colours from `last_seen` timestamps — this gives smooth colour transitions even between 2 s WebSocket updates
- Colour logic is **entirely client-side**: the backend only sends `last_seen` timestamps

---

## Adding a New Feature

### Adding a new backend monitor

1. Create `backend/monitors/your_monitor.py` following the pattern of `ping_monitor.py`
2. Add startup/shutdown in `backend/main.py` inside the `lifespan()` context
3. Broadcast results via `ws_manager.broadcast({...})`

### Adding a new frontend component

1. Create `frontend/src/components/YourComponent.tsx`
2. Add state to `networkStore.ts` if needed
3. Handle new WebSocket message types in `useWebSocket.ts`

### Adding a new API endpoint

1. Create a router in `backend/api/your_routes.py`
2. Include it in `backend/main.py`: `app.include_router(your_router)`

---

## Building for Production

### Frontend build

```bash
cd frontend
npm run build
```

Output goes to `frontend/dist/` — the FastAPI backend serves these static files automatically.

### Docker build

```bash
docker compose build
docker compose up -d
```

The Dockerfile uses a multi-stage build:
1. **Stage 1** (Node 22): builds the React frontend
2. **Stage 2** (Python 3.13): installs backend deps, copies built frontend

### Running with Docker

```bash
# Start
docker compose up -d

# View logs
docker compose logs -f netmap

# Stop
docker compose down
```

Access at **http://localhost:8585** (or change `NETMAP_PORT` in `.env`).

---

## Testing

### Backend — config loader

```bash
source .venv/bin/activate
python -c "
import sys; sys.path.insert(0, 'backend')
from config import NetMapConfig
cfg = NetMapConfig('config/netmap.yaml')
print(f'{len(cfg.devices)} devices, {len(cfg.links)} links')
"
```

### Backend — single ping sweep

```bash
source .venv/bin/activate
python -c "
import sys, asyncio; sys.path.insert(0, 'backend')
from config import NetMapConfig
from monitors.ping_monitor import PingMonitor
cfg = NetMapConfig('config/netmap.yaml')
async def test():
    pm = PingMonitor(cfg.devices)
    for s in await pm._sweep():
        print(f'{s.device_id:20s} {\"UP\" if s.is_alive else \"DOWN\":4s} rtt={s.rtt_ms or \"-\"}')
asyncio.run(test())
"
```

### Frontend — type check

```bash
cd frontend
npx tsc --noEmit
```

### Frontend — build check

```bash
cd frontend
npm run build
```

### API — health check

```bash
curl http://localhost:8585/api/health
```

---

## Troubleshooting

### Ping shows all devices as DOWN

- **macOS**: `icmplib` uses UDP fallback (`privileged=False`). Some hosts may not respond to UDP pings. Try running the backend with `sudo` for raw ICMP sockets.
- **Docker**: The container runs as root by default, so raw ICMP should work.
- **Firewall**: Ensure outbound ICMP is not blocked.

### WebSocket shows DISCONNECTED

- Check that the backend is running on port 8585
- Check browser console for WebSocket errors
- Ensure the Vite proxy config in `vite.config.ts` points to the correct backend port

### Frontend shows blank page

- Run `npm run build` and check for TypeScript errors
- Check browser console for JavaScript errors
- Ensure `vis-network` is installed: `npm ls vis-network`

---

## Code Style

- **Python**: Standard library style, type hints on all public functions
- **TypeScript**: Strict mode, no `any` in component props (utility types allowed)
- **Commits**: Conventional-ish: `feat:`, `fix:`, `docs:`, `refactor:`
