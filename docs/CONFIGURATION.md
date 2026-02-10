# Configuration Reference

All configuration lives in `config/netmap.yaml`. Passwords and secrets should use `${ENV_VAR}` references — the loader expands them from environment variables (or `.env` file).

---

## Full Example

```yaml
server:
  host: 0.0.0.0
  port: 8585
  cors_origins: ["*"]

ping:
  interval: 2
  timeout: 1

thresholds:
  - max_seconds: 5
    color: "#22C55E"
    label: "Online"
  - max_seconds: 10
    color: "#FFFF00"
    label: "Degraded"
  - max_seconds: 15
    color: "#FFD700"
  - max_seconds: 20
    color: "#FF8C00"
  - max_seconds: 25
    color: "#FF6600"
  - max_seconds: 30
    color: "#CC4400"
  - max_seconds: 180
    color: "#EF4444"
    label: "Down"

api_defaults:
  username: admin
  api_type: classic       # "rest" for HTTPS/443 or "classic" for port 8728
  port: 8728

devices:
  - name: core-router
    host: 10.0.0.1
    type: router
    profile: ccr
    password: "${CORE_PASS}"
    map: main
    position: {x: 400, y: 200}

maps:
  - name: main
    label: "Network Overview"

links:
  - from: core-router:ether1
    to: switch-1:sfp1
    speed: 10000
    type: wired

discovery:
  enabled: true
  interval: 300
  protocols: [mndp, lldp]
  auto_add_devices: false
  auto_add_links: true
```

---

## Section Reference

### `server`

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `host` | string | `0.0.0.0` | Bind address |
| `port` | int | `8585` | HTTP/WebSocket port |
| `cors_origins` | list | `["*"]` | Allowed CORS origins |

### `ping`

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `interval` | float | `2` | Seconds between ping sweeps |
| `timeout` | float | `1` | Seconds before a ping is considered lost |

**Note:** Interval should be > timeout. With 100+ devices, keep interval ≥ 2 to avoid overlapping sweeps.

### `thresholds`

Ordered list of colour thresholds. The frontend checks elapsed time since `last_seen` against each entry and uses the first match.

| Key | Type | Required | Description |
|-----|------|----------|-------------|
| `max_seconds` | float | yes | Maximum elapsed seconds for this colour |
| `color` | string | yes | Hex colour code (e.g. `"#22C55E"`) |
| `label` | string | no | Status label (e.g. "Online", "Down") |

**Default thresholds** (used if section is omitted):

```
 5s  → #22C55E (green)     — Online
10s  → #FFFF00 (bright yellow)
15s  → #FFD700 (yellow)
20s  → #FF8C00 (bright orange)
25s  → #FF6600 (orange)
30s  → #CC4400 (dark orange)
180s → #EF4444 (red)       — Down
```

You can customise these. For example, a stricter 3-level system:

```yaml
thresholds:
  - {max_seconds: 5, color: "#22C55E", label: "Online"}
  - {max_seconds: 30, color: "#FFAA00", label: "Warning"}
  - {max_seconds: 60, color: "#EF4444", label: "Down"}
```

### `api_defaults`

Default values applied to all devices that don't override them.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `username` | string | `admin` | RouterOS API username |
| `api_type` | string | `rest` | `rest` (RouterOS 7.1+) or `classic` (port 8728) |
| `port` | int | `443` | API port (443 for REST, 8728 for classic) |

### `devices`

List of MikroTik devices to monitor.

| Key | Type | Required | Default | Description |
|-----|------|----------|---------|-------------|
| `name` | string | yes | — | Unique device identifier (shown on map) |
| `host` | string | yes | — | IP address or hostname |
| `type` | string | no | `router` | `router`, `switch`, `ap`, `server`, `other` |
| `username` | string | no | from api_defaults | RouterOS API username |
| `password` | string | no | `""` | RouterOS API password (use `${ENV_VAR}`) |
| `api_type` | string | no | from api_defaults | `rest` or `classic` |
| `port` | int | no | from api_defaults | API port |
| `profile` | string | no | `edge` | Device profile: `ccr`, `crs`, `edge`, `vpn` |
| `map` | string | no | `main` | Which map this device belongs to |
| `position` | object | no | `{x: 0, y: 0}` | Position on the map canvas |

**Device types** determine the SVG icon on the map:

| Type | Icon |
|------|------|
| `router` | Box with routing arrows |
| `switch` | Rectangular with port LEDs |
| `ap` | Dome with WiFi waves |
| `server` | Tower with drive bays |
| `other` | Monitor screen |

Each icon includes a coloured status dot (bottom-right) that reflects the device's ping state.

**Example with environment variable:**

```yaml
devices:
  - name: vpn-gateway
    host: 10.0.0.1
    type: router
    profile: vpn
    password: "${VPN_GW_PASSWORD}"
    position: {x: 500, y: 300}
```

Then in `.env`:
```
VPN_GW_PASSWORD=mysecretpassword
```

### `maps`

Map/submap definitions for hierarchical navigation.

| Key | Type | Required | Default | Description |
|-----|------|----------|---------|-------------|
| `name` | string | yes | — | Unique map identifier |
| `label` | string | no | `""` | Display name |
| `parent` | string | no | `null` | Parent map name (for submap hierarchy) |
| `background` | string | no | `null` | Path to background image |

A default `main` map is created if this section is omitted.

**Submap example:**

```yaml
maps:
  - name: main
    label: "All Sites"
  - name: hq
    label: "Headquarters"
    parent: main
    background: "backgrounds/hq-floorplan.png"
  - name: branch-sofia
    label: "Sofia Branch"
    parent: main
```

### `links`

Manual link definitions between devices. Format: `device-name:interface-name`.

| Key | Type | Required | Default | Description |
|-----|------|----------|---------|-------------|
| `from` | string | yes | — | Source `device:interface` |
| `to` | string | yes | — | Destination `device:interface` |
| `speed` | int | no | `1000` | Link speed in Mbps |
| `type` | string | no | `wired` | `wired`, `wireless`, `vpn` |

**Link types** control edge rendering:

| Type | Line Style | Use For |
|------|-----------|---------|
| `wired` | Solid | Ethernet, fibre |
| `wireless` | Dashed | Wi-Fi, PtP radio |
| `vpn` | Dotted | IPsec, L2TP, WireGuard tunnels |

**Link width** is automatically computed from speed:

| Speed | Width |
|-------|-------|
| < 1 Gbps | Thin (1.5 px) |
| 1 Gbps | Medium (2.5 px) |
| 10 Gbps | Thick (4 px) |
| 25+ Gbps | Extra thick (6 px) |

### `discovery`

Auto-discovery settings. Queries `/ip/neighbor` on devices that have API credentials (password set). Discovered topology is persisted to `config/discovered_topology.json`.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `enabled` | bool | `true` | Enable MNDP/LLDP neighbour discovery |
| `interval` | int | `300` | Re-discover every N seconds |
| `protocols` | list | `[mndp, lldp]` | Protocols to use |
| `auto_add_devices` | bool | `false` | Auto-add discovered unknown devices |
| `auto_add_links` | bool | `true` | Auto-create links from neighbour data |

---

## Environment Variables

Set in `.env` file (or system environment):

| Variable | Description |
|----------|-------------|
| `NETMAP_PORT` | Docker published port (default: 8585) |
| `NETMAP_CONFIG` | Config file path override (default: `config/netmap.yaml`) |
| `*_PASS` | Device passwords referenced as `${*_PASS}` in config |

**Security:** Never commit `.env` or `config/netmap.yaml` with real passwords. Both are in `.gitignore`.

---

## Config Validation

The config loader validates on startup. Common errors:

| Error | Cause | Fix |
|-------|-------|-----|
| `FileNotFoundError` | Config file missing | Copy `netmap.example.yaml` → `netmap.yaml` |
| `ValidationError` | Invalid device type | Use: `router`, `switch`, `ap`, `server`, `other` |
| `ValidationError` | Invalid link type | Use: `wired`, `wireless`, `vpn` |
| Empty `${VAR}` | Env var not set | Add to `.env` file |
