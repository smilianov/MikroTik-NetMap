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

### Topology & Traffic (Phase 2 — planned)
- Auto-discovery via MNDP / LLDP (`/ip/neighbor`)
- Animated traffic-flow particles on links
- Link colour by utilisation (green → yellow → red)
- Line styles: solid = wired, dashed = wireless, dotted = VPN
- Drag-to-reposition with position persistence

### Device Dashboard & Submaps (Phase 3 — planned)
- Slide-in dashboard: CPU, memory, temperature, per-interface sparklines
- Submap hierarchy with full multi-level status cascade (improves The Dude's 1-level limit)
- Custom map backgrounds (floor plans, geographic images)
- Optional Grafana iframe embedding for deep metrics

### Polish & Scale (Phase 4 — planned)
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

---

## Project Structure

```
MTM-MultiView-LS/
├── backend/
│   ├── main.py                  # FastAPI entry point + WebSocket
│   ├── config.py                # YAML config loader
│   ├── models.py                # Pydantic data models
│   ├── monitors/
│   │   └── ping_monitor.py      # Async ICMP ping (2 s interval)
│   ├── api/
│   │   ├── websocket.py         # WebSocket connection manager
│   │   └── devices.py           # REST device endpoints
│   ├── mikrotik/
│   │   └── client.py            # Async RouterOS REST API client
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
| GET | `/api/health` | Health check (device count, WS clients, ping status) |
| GET | `/api/devices` | All devices with current ping state |
| GET | `/api/devices/{id}` | Single device detail |
| GET | `/api/config` | Thresholds, maps, links for frontend |

### WebSocket

Connect to `ws://host:8585/ws`. On connect, the server sends:
1. `ping_state` — current state of all devices
2. `config` — thresholds, device list, link definitions

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
