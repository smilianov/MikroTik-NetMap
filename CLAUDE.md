# MikroTik-NetMap

## Repositories
- **GitHub:** [smilianov/MikroTik-NetMap](https://github.com/smilianov/MikroTik-NetMap)
- **GitLab:** [autonomous-trio/MikroTik-NetMap](https://10.0.0.60/autonomous-trio/MikroTik-NetMap) (internal)
- **Remotes:** `origin` = GitHub, `gitlab` = GitLab (HTTPS + token, sslVerify=false)

## Project Overview
Real-time MikroTik network topology dashboard — a web-based alternative to The Dude.
FastAPI backend + React 19 frontend + vis-network graph + Docker deployment.

## Tech Stack
- **Backend:** Python 3.13, FastAPI, uvicorn, icmplib, routeros_api, httpx, asyncssh
- **Frontend:** React 19, TypeScript, Vite 7, Zustand, vis-network 10
- **Deploy:** Docker (multi-stage: Node 22 + Python 3.13), single container
- **Config:** YAML with `${ENV_VAR}` expansion for secrets

## Key Paths
- Backend entry: `backend/main.py`
- Config loader: `backend/config.py`
- Auth: `backend/auth.py` (SessionManager + Grafana API validation)
- Ping monitor: `backend/monitors/ping_monitor.py`
- Discovery: `backend/monitors/topology_discovery.py`
- Traffic: `backend/monitors/traffic_monitor.py`
- MikroTik client: `backend/mikrotik/client.py` (REST + Classic + SSH)
- Frontend app: `frontend/src/App.tsx`
- Network map: `frontend/src/components/NetworkMap.tsx`
- WebSocket hook: `frontend/src/hooks/useWebSocket.ts`
- Network store: `frontend/src/stores/networkStore.ts`
- Auth store: `frontend/src/stores/authStore.ts`
- Production config: `config/netmap.yaml` (git-ignored)
- Example config: `config/netmap.example.yaml`

## Commands
```bash
# Backend dev
cd backend && python -m uvicorn main:app --host 0.0.0.0 --port 8585 --reload

# Frontend dev
cd frontend && npm run dev

# Frontend build
cd frontend && npm run build

# Frontend type check
cd frontend && npx tsc --noEmit

# Docker build + run
docker build -t mikrotik-netmap .
docker run -d --name netmap --network host -v $(pwd)/config:/app/config mikrotik-netmap
```

## Deployment
- **Server:** 10.0.0.92, SSH user: `claude`, path: `/opt/MikroTik-NetMap/`
- **Container:** `netmap`, `--network host`, config volume-mounted at `/app/config`
- **Deploy flow:** rsync source (exclude `config/`) → `docker build` → `docker stop/rm/run`
- **Important:** Only `config/` is volume-mounted. Code changes require rebuilding the Docker image — `docker restart` alone won't pick them up.

## Architecture Notes
- Auth is optional (`auth.enabled: false` by default). `no-auth` branch preserves pre-auth state.
- Auth validates against Grafana API (`GET /api/user` with Basic Auth). Any Grafana user can log in.
- Sessions are in-memory (dict), HttpOnly cookies, 8h TTL.
- AuthMiddleware protects `/api/*` routes. WebSocket auth checks cookie after `accept()`.
- Right-click context menu uses native DOM `contextmenu` listener (not vis-network's `oncontext`).
- Context menu only works when the padlock is unlocked (editing mode).
- WS close code 4401 triggers frontend logout instead of reconnect.
- Custom device positions, device-map assignments, map labels, and custom maps persist as JSON files in `config/`.
- Discovered topology persists in `config/discovered_topology.json`.
- Frontend animation loop runs at ~10fps via requestAnimationFrame, reads from refs (not state) to avoid re-renders.

## Git Branches
- `main` — current development (with auth)
- `no-auth` — snapshot before auth was added (commit 3a0e8da)

## Related Projects
- **Monitoring-Codex** (`/Users/gun/Documents/Projects/Coding Projects/Claude_ai/Monitoring-Codex`) — Grafana + Prometheus stack
- **MikroTik-Telemetry** (`/Users/gun/Documents/Projects/Coding Projects/Claude_ai/MikroTik-Telemetry`) — Python telemetry collector
