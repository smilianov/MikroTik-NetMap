# MTM-MultiView-LS

**Real-time MikroTik network topology dashboard** — a web-based alternative to [The Dude](https://mikrotik.com/thedude) with graduated ping-status colours, interactive topology maps, and per-interface traffic visibility.

Part of the **MTM by LS** monitoring suite alongside [Monitoring-Codex](https://github.com/smilianov/Monitoring-Codex) and [MikroTik-Telemetry](https://github.com/smilianov/MikroTik-Telemetry).

---

## Features

### Live Ping Map (Phase 1 — current)
- **2-second ICMP ping** for every device — far faster than The Dude's 30 s cycle
- **7-level graduated colour system** that transitions smoothly in the browser:

  | Elapsed | Colour | Hex |
  |---------|--------|-----|
  | < 5 s | Green | `#22C55E` |
  | 5 s | Bright Yellow | `#FFFF00` |
  | 10 s | Yellow | `#FFD700` |
  | 15 s | Bright Orange | `#FF8C00` |
  | 20 s | Orange | `#FF6600` |
  | 30 s | Dark Orange | `#CC4400` |
  | 3 min | RED | `#EF4444` |

- **Interactive vis-network graph** — zoom, pan, hover tooltips
- **Device sidebar** with search, sorted by status
- **Status bar** showing online / degraded / offline counts and live WebSocket indicator
- **Double-click drill-down** panel with device details
- **YAML config** with `${ENV_VAR}` secret expansion

### Topology Discovery (Phase 2 — current)
- **Auto-discovery** via MNDP / LLDP — queries `/ip/neighbor` on devices with API credentials
- **Both REST API** (HTTPS port 443, RouterOS 7.1+) **and Classic API** (port 8728, RouterOS 6.49+)
- **Half-link matching** — combines neighbour reports from both sides into full bidirectional links
- **Auto-positioning** — discovered devices placed in a circle around their parent device
- **Persistence** — discovered topology saved to `config/discovered_topology.json` (survives restarts)
- **SVG device icons** — routers, switches, APs, servers rendered as distinct icons with coloured status dots
- Line styles: solid = wired, dashed = wireless, dotted = VPN

### Device Dashboard & Submaps (Phase 3 — planned)
- Slide-in dashboard: CPU, memory, temperature, per-interface sparklines
- Submap hierarchy with full multi-level status cascade (improves The Dude's 1-level limit)
- Custom map backgrounds (floor plans, geographic images)
- Optional Grafana iframe embedding for deep metrics

### Traffic Visualisation (Phase 3 — planned)
- Animated traffic-flow particles on links
- Link colour by utilisation (green → yellow → red)
- Drag-to-reposition with position persistence

### Device Dashboard & Submaps (Phase 4 — planned)
- Slide-in dashboard: CPU, memory, temperature, per-interface sparklines
- Submap hierarchy with full multi-level status cascade
- Custom map backgrounds (floor plans, geographic images)
- Optional Grafana iframe embedding for deep metrics

### Polish & Scale (Phase 5 — planned)
- Right-click context menu (ping, reboot, open in WinBox / Grafana)
- Browser notifications on state change
- Config hot-reload
- Prometheus metric push (integrate with Monitoring-Codex)
- Tiered scaling: 5–20 → 20–100 → 100+ devices

---

## Quick Start

### Prerequisites
- Python 3.13+
- Node.js 22+ (for frontend development)
- Git

### 1. Clone & configure

```bash
git clone git@github.com:smilianov/MTM-MultiView-LS.git
cd MTM-MultiView-LS

cp config/netmap.example.yaml config/netmap.yaml
cp .env.example .env
# Edit config/netmap.yaml — add your MikroTik devices
# Edit .env — set device passwords
```

### 2. Run (development)

**Terminal 1 — Backend:**
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt

cd backend
python -m uvicorn main:app --host 0.0.0.0 --port 8585 --reload
```

**Terminal 2 — Frontend:**
```bash
cd frontend
npm install
npm run dev
```

Open **http://localhost:5173** — the Vite dev server proxies `/api` and `/ws` to the backend.

### 3. Run (Docker)

```bash
docker compose up -d
```

Open **http://localhost:8585** — single container serves both backend and frontend.

### 4. Deploy to a server

```bash
# Copy project to server
rsync -avz --exclude='node_modules/' --exclude='.venv/' --exclude='__pycache__/' \
  --exclude='frontend/dist/' --exclude='.git/' \
  . user@server:/opt/MTM-MultiView-LS/

# SSH into server
ssh user@server

# Create production config
cd /opt/MTM-MultiView-LS
cp config/netmap.example.yaml config/netmap.yaml
# Edit config/netmap.yaml — set real device IPs, credentials, enable discovery

# Build and run
docker build -t mikrotik-netmap:latest .
docker run -d --name netmap \
  -p 8585:8585 \
  -v $(pwd)/config:/app/config \
  --restart unless-stopped \
  mikrotik-netmap:latest
```

Open **http://server-ip:8585** in your browser.

### 5. Enable topology discovery

In `config/netmap.yaml`, give at least one device API credentials and enable discovery:

```yaml
api_defaults:
  username: prometheus
  api_type: classic       # "classic" for port 8728, "rest" for HTTPS/443
  port: 8728

devices:
  - name: core-router
    host: 10.0.0.1
    type: router
    profile: ccr
    password: "your-api-password"
    map: main
    position: {x: 400, y: 200}

discovery:
  enabled: true
  interval: 300             # re-discover every 5 minutes
  auto_add_devices: true    # add neighbours to the map automatically
  auto_add_links: true      # show discovered links on the map
```

The tool queries `/ip/neighbor` on every device with credentials and builds the topology graph automatically. Discovered devices and links persist across restarts in `config/discovered_topology.json`.

---

## Project Structure

```
MTM-MultiView-LS/
├── backend/
│   ├── main.py                  # FastAPI entry point + WebSocket
│   ├── config.py                # YAML config loader
│   ├── models.py                # Pydantic data models
│   ├── monitors/
│   │   ├── ping_monitor.py      # Async ICMP ping (2 s interval)
│   │   └── topology_discovery.py # MNDP/LLDP neighbour discovery
│   ├── api/
│   │   ├── websocket.py         # WebSocket connection manager
│   │   └── devices.py           # REST device endpoints
│   ├── mikrotik/
│   │   └── client.py            # RouterOS API client (REST + Classic)
│   └── requirements.txt
│
├── frontend/
│   ├── src/
│   │   ├── App.tsx              # Root layout
│   │   ├── components/
│   │   │   ├── NetworkMap.tsx    # vis-network topology canvas
│   │   │   ├── StatusBar.tsx     # Online/offline counts
│   │   │   ├── Sidebar.tsx       # Searchable device list
│   │   │   └── DevicePanel.tsx   # Slide-in detail panel
│   │   ├── hooks/
│   │   │   └── useWebSocket.ts   # Auto-reconnect WebSocket
│   │   ├── stores/
│   │   │   └── networkStore.ts   # Zustand state management
│   │   └── utils/
│   │       ├── colorThresholds.ts # Graduated colour logic
│   │       ├── deviceIcons.ts     # SVG device icon generator
│   │       └── formatters.ts      # Duration / bandwidth display
│   ├── package.json
│   └── vite.config.ts
│
├── config/
│   ├── netmap.yaml              # Your config (git-ignored)
│   └── netmap.example.yaml      # Template
│
├── Dockerfile                   # Multi-stage Node + Python build
├── docker-compose.yml
├── .env.example
│
├── docs/
│   ├── ARCHITECTURE.md          # System design & data flow
│   └── CONFIGURATION.md         # Config reference
│
└── DEVELOPMENT.md               # Dev setup & contribution guide
```

---

## Tech Stack

| Layer | Technology | Why |
|-------|-----------|-----|
| Backend | Python 3.13 + FastAPI | Async-native, WebSocket built-in, matches MTM ecosystem |
| Ping | icmplib (async) | Pure Python ICMP, no root required (UDP fallback) |
| Frontend | React 19 + Vite | Modern, fast HMR |
| Graph | vis-network | Purpose-built network topology: physics, clustering, shapes |
| State | Zustand | Lightweight, no boilerplate |
| Real-time | WebSocket | Backend pushes every 2 s, frontend interpolates at 10 fps |
| Config | YAML | Consistent with MikroTik-Telemetry / Monitoring-Codex |
| Deploy | Docker Compose | Single container, volume-mount config |

---

## API Reference

### REST

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/health` | Health check (devices, WS clients, ping/discovery status) |
| GET | `/api/devices` | All devices with current ping state |
| GET | `/api/devices/{id}` | Single device detail |
| GET | `/api/config` | Thresholds, maps, links for frontend |

### WebSocket

Connect to `ws://host:8585/ws`. On connect, the server sends:
1. `ping_state` — current state of all devices
2. `config` — thresholds, device list, link definitions (including discovered)

Then every 2 seconds:
```json
{
  "type": "ping_state",
  "timestamp": "2026-02-10T12:00:00Z",
  "devices": [
    {"id": "core-router", "last_seen": "2026-02-10T12:00:00Z", "rtt_ms": 1.2, "is_alive": true}
  ]
}
```

When topology changes are detected (after a discovery sweep):
```json
{
  "type": "topology_update",
  "timestamp": "2026-02-10T12:05:00Z",
  "added_devices": [{"id": "switch-dc3", "name": "switch-dc3", "host": "10.0.0.5", ...}],
  "added_links": [{"from": "core-router:ether3", "to": "switch-dc3:ether1", ...}],
  "removed_links": []
}
```

---

## Related Projects

| Project | Description |
|---------|-------------|
| [Monitoring-Codex](https://github.com/smilianov/Monitoring-Codex) | Grafana + Prometheus + Loki monitoring stack for MikroTik |
| [MikroTik-Telemetry](https://github.com/smilianov/MikroTik-Telemetry) | Python telemetry collector (Splunk HEC / Syslog / Prometheus) |

---

## License

MIT

---

*MTM by LS — MikroTik Monitoring by LogicSoft*
