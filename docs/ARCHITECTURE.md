# Architecture

## System Overview

MTM-MultiView-LS is a single-container web application that pings MikroTik devices every 2 seconds, auto-discovers network topology via MNDP/LLDP, and renders an interactive network map in the browser with real-time colour-coded status.

```
┌──────────────────────────────────────────────────────────────┐
│                     MTM-MultiView-LS                          │
│                                                              │
│  ┌──────────────────────┐    ┌────────────────────────────┐  │
│  │   Frontend (React)   │◄──►│   Backend (FastAPI)         │  │
│  │                      │ WS │                             │  │
│  │  vis-network graph   │    │  PingMonitor    (2 s ICMP)  │  │
│  │  SVG device icons    │    │  TopologyDiscovery (5 min)  │  │
│  │  Zustand store       │    │  WebSocket broadcaster      │  │
│  │  Colour interpolation│    │  REST API                   │  │
│  └──────────────────────┘    └──────────┬─────────────────┘  │
│                                         │                    │
└─────────────────────────────────────────┼────────────────────┘
                                          │  ICMP + RouterOS API
                     ┌────────────────────┼────────────────────┐
                     ▼                    ▼                    ▼
               ┌──────────┐        ┌──────────┐        ┌──────────┐
               │ Router 1 │────────│ Switch 1 │────────│ Router 2 │
               └──────────┘        └──────────┘        └──────────┘
                    │ /ip/neighbor       │                    │
                    └───── discovers ────┴──── all neighbours ┘
```

---

## Component Breakdown

### Backend

#### `main.py` — Application entry point

- Creates the FastAPI app with a **lifespan** context manager
- On startup: loads config, starts PingMonitor, wires up WebSocket manager
- On shutdown: stops PingMonitor gracefully
- Mounts static files from `frontend/dist/` when present (production mode)
- Registers REST routes and the `/ws` WebSocket endpoint

#### `config.py` — Configuration loader

- Reads `netmap.yaml` with PyYAML
- Expands `${ENV_VAR}` references from environment (for secrets)
- Parses into typed Pydantic models: `DeviceConfig`, `LinkConfig`, `MapConfig`, `ThresholdConfig`
- Falls back to sensible defaults for missing sections

#### `monitors/ping_monitor.py` — ICMP ping engine

- Uses `icmplib.async_ping` for non-blocking ICMP
- Pings all devices concurrently every `interval` seconds (default 2 s)
- Maintains a `states` dict mapping device name → `PingState`
- Calls an `on_update` callback after each sweep (used to trigger WebSocket broadcast)
- Runs with `privileged=False` (UDP fallback — no root needed on macOS)

#### `api/websocket.py` — Connection manager

- Tracks all connected WebSocket clients
- `broadcast()` sends JSON to all clients; automatically removes dead connections
- Thread-safe via `asyncio.Lock`

#### `api/devices.py` — REST endpoints

- `GET /api/devices` — all devices with current ping state
- `GET /api/devices/{id}` — single device
- Reads from shared app state (config + ping monitor)

#### `monitors/topology_discovery.py` — MNDP/LLDP discovery engine

- Queries `/ip/neighbor` on every device that has API credentials
- Runs every `interval` seconds (default 300 = 5 min) as an `asyncio.Task`
- Collects **half-links** (Device A sees B on ether1) and matches them into **full links**
- Detects topology changes: added devices, added links, removed links
- Auto-positions newly discovered devices in a circle around their parent
- Persists discoveries to `config/discovered_topology.json` (survives restarts)
- Calls `on_update` callback to broadcast changes via WebSocket

#### `mikrotik/client.py` — RouterOS API client

- **`MikroTikClient`** — async REST client using `httpx` (HTTPS port 443, RouterOS 7.1+)
- **`MikroTikClassicClient`** — async wrapper around `routeros_api` library (port 8728, RouterOS 6.49+); synchronous calls wrapped in `asyncio.to_thread()`
- **`create_client()`** — factory function that picks the right client based on `api_type`
- Methods: `get_neighbors()`, `get_interfaces()`, `get_system_resource()`, `close()`

### Frontend

#### `components/NetworkMap.tsx` — Topology canvas

- Initialises a `vis-network` `Network` instance inside a `<div>`
- Syncs devices from Zustand store → vis `DataSet` nodes
- Syncs links → vis edges (with width by speed, dashes by type)
- Runs a **~10 fps animation loop** via `requestAnimationFrame` that:
  1. Reads `last_seen` timestamps from the store
  2. Computes elapsed seconds for each device
  3. Maps elapsed time → colour via `getPingColor()`
  4. Updates vis node colours
- Physics disabled (uses fixed positions from config)
- Double-click fires `selectDevice()` to open detail panel

#### `components/StatusBar.tsx` — Header

- Counts devices by status: online (< 5 s), degraded (5–30 s), offline (> 30 s), unknown
- Shows WebSocket connection status indicator (LIVE / DISCONNECTED)

#### `components/Sidebar.tsx` — Device list

- Searchable by name or IP
- Sorted: alive first, then alphabetical
- Click selects device (highlights on map + opens panel)
- Shows status dot colour and RTT

#### `components/DevicePanel.tsx` — Detail panel

- Slide-in from right on double-click
- Shows: name, host, type, profile, RTT, status, last seen
- Phase 2 will add: interface list, traffic sparklines, system health

#### `hooks/useWebSocket.ts` — WebSocket connection

- Connects to `ws://host/ws` on mount
- Auto-reconnects after 3 s on disconnect
- Dispatches `config` messages → `setConfig()` (one-time on connect)
- Dispatches `ping_state` messages → `updatePingState()` (every 2 s)
- Dispatches `topology_update` messages → `mergeTopology()` (after discovery sweeps)

#### `stores/networkStore.ts` — Zustand state

- `devices` — device info from config + discovered (name, host, type, position)
- `links` — link definitions (manual + discovered)
- `thresholds` — colour thresholds from server
- `pingData` — real-time ping state per device (last_seen, rtt, is_alive)
- `selectedDevice` — currently selected device ID (for detail panel)
- `wsConnected` — WebSocket connection status
- `mergeTopology()` — incrementally adds discovered devices/links without replacing config entries

#### `utils/colorThresholds.ts` — Colour engine

- `getPingColor(lastSeen, thresholds)` — maps elapsed seconds to hex colour
- `getPingLabel()` — human-readable status text
- `getPulseSpeed()` — CSS animation duration (faster = more urgent)
- Runs client-side at frame rate — no server computation needed

---

## Data Flow

### Ping cycle (every 2 seconds)

```
PingMonitor._sweep()
  └── async_ping(device.host) × N devices (concurrent)
       └── Update self.states[device.name].last_seen / rtt_ms / is_alive

PingMonitor → on_update callback
  └── ws_manager.broadcast({type: "ping_state", devices: [...]})
       └── WebSocket → all connected browsers

Browser: useWebSocket.handleMessage()
  └── networkStore.updatePingState(devices)
       └── NetworkMap animation loop reads pingData
            └── getPingColor(last_seen) → node.color update
```

### Discovery cycle (every 5 minutes by default)

```
TopologyDiscovery._sweep()
  └── create_client(host, api_type) → REST or Classic client
       └── client.get_neighbors() × N devices (concurrent)
            └── Collect half-links: "A sees B on ether1"
                 └── Match half-links into full links
                      └── Detect changes (added/removed devices & links)

TopologyDiscovery → on_update callback
  └── PingMonitor.add_device() for new devices
  └── ws_manager.broadcast({type: "topology_update", ...})
       └── WebSocket → all connected browsers

Browser: useWebSocket.handleMessage()
  └── networkStore.mergeTopology(added_devices, added_links, removed_links)
       └── NetworkMap renders new nodes + edges
```

### Initial connection

```
Browser connects to ws://host/ws
  └── Server sends: {type: "ping_state", ...}  (current state)
  └── Server sends: {type: "config", ...}       (thresholds, devices, links)

Frontend:
  └── setConfig() populates devices, links, thresholds
  └── updatePingState() populates pingData
  └── NetworkMap renders nodes + edges
  └── Animation loop starts colour updates
```

---

## Design Decisions

### Why not Grafana?

Grafana's Node Graph panel can render topology but lacks:
- Sub-5-second refresh for graduated colour transitions
- Smooth client-side colour interpolation
- Interactive double-click drill-down to device dashboards
- Custom animated traffic-flow particles

We still integrate with Monitoring-Codex's Grafana for deep metrics (Phase 3 iframe embedding).

### Why vis-network?

- Purpose-built for interactive network graphs
- Built-in: physics simulation, clustering (100+ nodes), node shapes, edge labels
- Double-click, hover, drag-to-reposition events
- Active maintenance and large community

### Why client-side colour interpolation?

The backend sends `last_seen` timestamps. The frontend computes colours at ~10 fps. This means:
- Colours transition smoothly between 2 s WebSocket updates
- A device that stops responding gradually shifts through 7 colour stages in real-time
- Zero additional server CPU for colour logic
- Works even if a WebSocket update is delayed

### Why icmplib with privileged=False?

- No root/sudo required for development
- Uses UDP datagram sockets as ICMP fallback
- Works on macOS, Linux, and Docker without `NET_CAP_RAW`
- In Docker (running as root), raw ICMP is used automatically

---

## Scaling Strategy

| Tier | Devices | Ping Workers | Architecture |
|------|---------|-------------|-------------|
| Small | 5–20 | 1 async task | Single process, in-memory |
| Medium | 20–100 | 2–4 async tasks | Single process, SQLite for topology |
| Large | 100+ | 8+ workers | Multi-process, Redis for shared state |

The async ping design handles 100+ devices in a single sweep (all pings run concurrently via `asyncio.gather`). The bottleneck is the 1 s timeout per ping — with 100 devices, a sweep still completes in ~1 s.

---

## Integration with MTM Ecosystem

```
┌─────────────────────┐     ┌──────────────────────┐
│  MTM-MultiView-LS   │     │  Monitoring-Codex     │
│  (this project)     │     │  (Grafana stack)      │
│                     │     │                       │
│  Live topology map  │────►│  Deep device metrics  │
│  Ping monitoring    │     │  Log analysis         │
│  Traffic overview   │     │  Alert management     │
└─────────┬───────────┘     └───────────┬───────────┘
          │                             │
          │  RouterOS REST API          │  mktxp + Syslog
          │                             │
          ▼                             ▼
    ┌───────────────────────────────────────┐
    │          MikroTik Devices              │
    └───────────────────────────────────────┘
          ▲
          │  REST API for collectors
          │
┌─────────┴───────────┐
│  MikroTik-Telemetry  │
│  (Splunk / Syslog)   │
└──────────────────────┘
```
