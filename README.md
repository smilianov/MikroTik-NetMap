# MTM-MultiView-LS

**Real-time MikroTik network topology dashboard** — a web-based alternative to [The Dude](https://mikrotik.com/thedude) with graduated ping-status colours, auto-discovery, traffic-flow animation, multi-map tabs, and optional Grafana-based authentication.

Part of the **MTM by LS** monitoring suite alongside [Monitoring-Codex](https://github.com/smilianov/Monitoring-Codex) and [MikroTik-Telemetry](https://github.com/smilianov/MikroTik-Telemetry).

---

## Features

### Live Ping Map
- **2-second ICMP ping** for every device — far faster than The Dude's 30 s cycle
- **7-level graduated colour system** that transitions smoothly in the browser
- **Interactive vis-network graph** — zoom, pan, hover tooltips
- **SVG device icons** — routers, switches, APs, servers with coloured status dots
- **Drag-to-reposition** with position persistence (lock/unlock toggle)
- **Device sidebar** with search, sorted by status
- **Status bar** showing online / degraded / offline counts and live WebSocket indicator
- **Double-click drill-down** panel with device details

### Topology Discovery
- **Auto-discovery** via MNDP / LLDP — queries `/ip/neighbor` on devices with API credentials
- **Both REST API** (HTTPS port 443, RouterOS 7.1+) **and Classic API** (port 8728, RouterOS 6.49+)
- **SSH key authentication** support — no passwords needed (see [SSH_KEYS.md](docs/SSH_KEYS.md))
- **Half-link matching** — combines neighbour reports from both sides into full bidirectional links
- **Auto-positioning** — discovered devices placed in a circle around their parent
- **Persistence** — discovered topology saved to `config/discovered_topology.json`

### Traffic Visualisation
- **Animated traffic-flow particles** on links — particle count and speed reflect utilisation
- **Link colour by utilisation** (green → yellow → red)
- **Bandwidth tooltips** — TX/RX per interface on hover
- Line styles: solid = wired, dashed = wireless, dotted = VPN

### Multi-Map Tabs
- **Multiple maps** — organise devices across tabs (e.g. Main, Floor 2, Building B)
- **Create / rename / delete** maps from the UI
- **Move devices between maps** via right-click context menu
- **Tab context menu** — right-click on a tab to rename or delete it
- Maps defined in YAML config + custom maps created from UI (persisted across restarts)

### Right-Click Context Menu
- **Unlock the padlock** to enable editing mode, then right-click on any device
- **Hide device** — temporarily remove from map (reversible from sidebar)
- **Move to map** — reassign device to a different map/tab
- **Remove device** — blacklist device permanently (won't reappear on rediscovery)
- **Manual links** — create/delete links between devices via UI
- Right-click on manual link edges to delete them

### Authentication (Optional)
- **Grafana API validation** — any user with a valid Grafana account can log in
- **Session-based auth** with HttpOnly cookies (8h TTL by default)
- **No separate user database** — leverages your existing Grafana instance from Monitoring-Codex
- **Auth optional** — disabled by default (`auth.enabled: false`); a `no-auth` branch is available
- Protected REST API and WebSocket connections

---

## Installation

For a **complete step-by-step guide** covering SSH key setup, Claude Code integration, and deploying to a fresh Ubuntu Server 24.04, see **[docs/INSTALLATION.md](docs/INSTALLATION.md)**.

---

## Quick Start

### Prerequisites
- Docker 27+ (recommended) or Python 3.13+ / Node.js 22+ for development
- One or more MikroTik devices on a reachable network
- (Optional) Grafana instance for authentication

### 1. Clone & configure

```bash
git clone git@github.com:smilianov/MTM-MultiView-LS.git
cd MTM-MultiView-LS

cp config/netmap.example.yaml config/netmap.yaml
cp .env.example .env
# Edit config/netmap.yaml — add your MikroTik devices
# Edit .env — set device passwords
```

### 2. Run with Docker Compose

```bash
docker compose up -d
```

Open **http://localhost:8585** — single container serves both backend and frontend.

### 3. Run in development

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

---

## Deploy to a Server

### Build and run

```bash
# Copy project to server (exclude dev files)
rsync -avz --exclude='node_modules/' --exclude='.venv/' --exclude='__pycache__/' \
  --exclude='frontend/dist/' --exclude='.git/' \
  . user@server:/opt/MTM-MultiView-LS/

# SSH into server
ssh user@server
cd /opt/MTM-MultiView-LS

# Create production config
cp config/netmap.example.yaml config/netmap.yaml
# Edit config/netmap.yaml — set real device IPs, credentials, enable discovery

# Build and run
docker build -t mikrotik-netmap:latest .
docker run -d --name netmap \
  --network host \
  -v $(pwd)/config:/app/config \
  --restart unless-stopped \
  mikrotik-netmap:latest
```

> **Note:** Use `--network host` if you need the container to reach a Grafana instance on the same host (for authentication) or if your MikroTik devices are on the host network. Otherwise use `-p 8585:8585`.

Open **http://server-ip:8585** in your browser.

### Update an existing deployment

```bash
# Sync source to server (exclude config to preserve production settings)
rsync -avz --exclude='node_modules/' --exclude='.venv/' --exclude='__pycache__/' \
  --exclude='frontend/dist/' --exclude='.git/' --exclude='config/' \
  . user@server:/opt/MTM-MultiView-LS/

# Rebuild image and recreate container
ssh user@server "cd /opt/MTM-MultiView-LS && \
  docker build -t mikrotik-netmap:latest . && \
  docker stop netmap && docker rm netmap && \
  docker run -d --name netmap --network host \
    -v /opt/MTM-MultiView-LS/config:/app/config \
    --restart unless-stopped mikrotik-netmap:latest"
```

### Enable authentication

Add to your production `config/netmap.yaml`:

```yaml
auth:
  enabled: true
  grafana_url: "http://localhost:3000"  # Your Grafana instance
  session_ttl: 28800                    # 8 hours
```

Any valid Grafana user can log in. The login page validates credentials against `GET /api/user` on your Grafana instance.

> **Tip:** A `no-auth` branch exists at the point before auth was added, if you want a deployment without any authentication.

### Enable topology discovery

```yaml
api_defaults:
  username: prometheus
  password: "your-api-password"
  api_type: classic       # "classic" for port 8728, "rest" for HTTPS/443
  port: 8728

discovery:
  enabled: true
  interval: 120           # re-discover every 2 minutes
  protocols: [mndp, lldp]
  auto_add_devices: true
  auto_add_links: true
```

### Enable traffic monitoring

```yaml
traffic:
  enabled: true
  interval: 10            # poll interface stats every 10 seconds
```

Requires API credentials on devices (via `api_defaults` or per-device `password`). Traffic is visualised as animated particles on links.

---

## Usage Guide

### Map Navigation
- **Scroll** to zoom in/out
- **Click + drag** on empty space to pan
- **Double-click** a device to open the detail panel
- **Click** on a tab to switch maps

### Editing Mode (Unlock the Padlock)
Click the padlock icon (top-right) to unlock editing:
- **Drag** devices to reposition (positions persist across restarts)
- **Right-click** a device for context menu: Hide, Move to map, Remove
- **Right-click** a manual link to delete it
- **Right-click** a map tab to rename or delete it
- Click the link icon to enter **manual link creation mode** (click two devices to connect)
- Click the padlock again to lock and prevent accidental changes

### Map Management
- **Double-click** a tab label to rename it inline
- Click the **+** button to create a new map
- Right-click a tab → **Delete** to remove it (devices move back to Main)

### Authentication
When auth is enabled, you'll see a login page. Enter your Grafana username and password. Sessions last 8 hours by default. The username and logout button appear in the status bar.

---

## Configuration Reference

See [docs/CONFIGURATION.md](docs/CONFIGURATION.md) for the full reference.

### Minimal production config

```yaml
server:
  host: 0.0.0.0
  port: 8585

ping:
  interval: 2
  timeout: 1

api_defaults:
  username: prometheus
  password: "your-api-password"
  api_type: classic
  port: 8728

devices:
  - name: core-router
    host: 10.0.0.1
    type: router
    profile: ccr
    map: main
    position: {x: 0, y: 0}

maps:
  - name: main
    label: "Network Overview"

links: []

discovery:
  enabled: true
  interval: 120
  auto_add_devices: true
  auto_add_links: true

traffic:
  enabled: true
  interval: 10

auth:
  enabled: false
```

---

## Project Structure

```
MTM-MultiView-LS/
├── backend/
│   ├── main.py                  # FastAPI app, middleware, WebSocket, routes
│   ├── config.py                # YAML config loader with ${ENV} expansion
│   ├── models.py                # Pydantic data models
│   ├── auth.py                  # Session manager + Grafana API validation
│   ├── visibility_manager.py    # Hide/blacklist device state
│   ├── manual_link_manager.py   # Manual link persistence
│   ├── monitors/
│   │   ├── ping_monitor.py      # Async ICMP ping (2 s interval)
│   │   ├── topology_discovery.py # MNDP/LLDP neighbour discovery
│   │   └── traffic_monitor.py   # Per-interface bandwidth polling
│   ├── api/
│   │   ├── auth.py              # Login/logout/session endpoints
│   │   ├── devices.py           # Device REST endpoints
│   │   ├── links.py             # Manual link CRUD
│   │   ├── visibility.py        # Hide/show/blacklist endpoints
│   │   └── websocket.py         # WebSocket connection manager
│   ├── mikrotik/
│   │   └── client.py            # RouterOS API client (REST + Classic + SSH)
│   └── requirements.txt
│
├── frontend/
│   ├── src/
│   │   ├── App.tsx              # Auth gating + root layout
│   │   ├── components/
│   │   │   ├── NetworkMap.tsx    # vis-network canvas with traffic particles
│   │   │   ├── StatusBar.tsx     # Device counts + username + logout
│   │   │   ├── Sidebar.tsx       # Searchable device list
│   │   │   ├── DevicePanel.tsx   # Slide-in detail panel
│   │   │   ├── ContextMenu.tsx   # Right-click device menu
│   │   │   ├── ConfirmDialog.tsx # Confirmation modal
│   │   │   ├── LinkDialog.tsx    # Manual link creation form
│   │   │   └── LoginPage.tsx     # Grafana auth login form
│   │   ├── hooks/
│   │   │   └── useWebSocket.ts   # Auto-reconnect WebSocket
│   │   ├── stores/
│   │   │   ├── networkStore.ts   # Zustand state management
│   │   │   └── authStore.ts      # Auth state (login/logout/session)
│   │   ├── api/
│   │   │   ├── visibility.ts     # Hide/blacklist/move API calls
│   │   │   ├── links.ts          # Manual link API calls
│   │   │   └── fetchWithAuth.ts  # Fetch wrapper (auto-logout on 401)
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
│   ├── INSTALLATION.md          # Full install guide (scratch to running)
│   ├── ARCHITECTURE.md          # System design & data flow
│   ├── CONFIGURATION.md         # Full config reference
│   └── SSH_KEYS.md              # SSH key setup for MikroTik devices
│
└── DEVELOPMENT.md               # Dev setup & contribution guide
```

---

## API Reference

### REST

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/api/health` | Public | Health check + stats |
| GET | `/api/config` | Protected | Thresholds, maps, links |
| GET | `/api/devices` | Protected | All devices with ping state |
| GET | `/api/devices/{id}` | Protected | Single device detail |
| PUT | `/api/devices/{id}/map` | Protected | Move device to a map |
| POST | `/api/maps` | Protected | Create a new map |
| PUT | `/api/maps/{name}/label` | Protected | Rename a map |
| DELETE | `/api/maps/{name}` | Protected | Delete a custom map |
| POST | `/api/visibility/hide/{id}` | Protected | Hide a device |
| POST | `/api/visibility/show/{id}` | Protected | Show a hidden device |
| POST | `/api/visibility/blacklist/{id}` | Protected | Blacklist a device |
| POST | `/api/links` | Protected | Create a manual link |
| DELETE | `/api/links/{id}` | Protected | Delete a manual link |
| POST | `/api/auth/login` | Public | Login (Grafana validation) |
| POST | `/api/auth/logout` | Public | Logout (destroy session) |
| GET | `/api/auth/me` | Public | Check session status |

### WebSocket

Connect to `ws://host:8585/ws`. When auth is enabled, the `netmap_session` cookie must be present (set automatically after login).

**Messages from server:**

| Type | When | Content |
|------|------|---------|
| `config` | On connect | Devices, maps, links, thresholds, visibility |
| `ping_state` | Every 2 s | Per-device last_seen, rtt_ms, is_alive |
| `traffic_state` | Every 10 s | Per-interface TX/RX bandwidth |
| `topology_update` | After discovery | Added/removed devices and links |
| `visibility_update` | On hide/show/blacklist | Updated hidden/blacklisted lists |
| `device_map_change` | On device move | device_id + new map |
| `map_label_change` | On tab rename | map_name + new label |
| `maps_changed` | On map create/delete | Full maps list |

**Messages from client:**

| Type | Description |
|------|-------------|
| `position_update` | `{device_id, position: {x, y}}` — drag-to-reposition |

---

## Tech Stack

| Layer | Technology | Why |
|-------|-----------|-----|
| Backend | Python 3.13 + FastAPI | Async-native, WebSocket built-in |
| Ping | icmplib (async) | Pure Python ICMP, no root required |
| Traffic | RouterOS API (REST + Classic) | Direct per-interface bandwidth polling |
| Frontend | React 19 + TypeScript + Vite | Modern, fast HMR |
| Graph | vis-network | Purpose-built network topology visualisation |
| State | Zustand | Lightweight, no boilerplate |
| Real-time | WebSocket | Backend pushes every 2 s, frontend renders at 10 fps |
| Auth | Grafana API | No separate user database needed |
| Config | YAML | Consistent with MikroTik-Telemetry / Monitoring-Codex |
| Deploy | Docker | Single container, volume-mount config |

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
