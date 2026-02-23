# Installation Guide — From Scratch to Running Dashboard

This guide covers everything from a blank machine to a fully running MikroTik-NetMap deployment, including SSH key setup, Claude Code integration, and remote server installation on Ubuntu Server 24.04.

---

## Table of Contents

1. [Prerequisites (Local Machine)](#1-prerequisites-local-machine)
2. [SSH Key Setup for Passwordless Login](#2-ssh-key-setup-for-passwordless-login)
3. [Clone the Project](#3-clone-the-project)
4. [Working with Claude Code](#4-working-with-claude-code)
5. [Prepare the Remote Server (Ubuntu 24.04)](#5-prepare-the-remote-server-ubuntu-2404)
6. [Deploy to the Remote Server](#6-deploy-to-the-remote-server)
7. [Configure the Application](#7-configure-the-application)
8. [Verify the Deployment](#8-verify-the-deployment)
9. [Update an Existing Deployment](#9-update-an-existing-deployment)
10. [Troubleshooting](#10-troubleshooting)

---

## 1. Prerequisites (Local Machine)

You need these tools on your development machine (macOS or Linux):

### Git

```bash
# macOS (Homebrew)
brew install git

# Ubuntu/Debian
sudo apt install git
```

### GitHub CLI

```bash
# macOS
brew install gh

# Ubuntu/Debian
sudo apt install gh

# Authenticate (one-time)
gh auth login
```

### Node.js 22+ and Python 3.13+

```bash
# macOS
brew install node python

# Ubuntu/Debian
sudo apt install nodejs npm python3 python3-venv
```

### Docker (optional, for local testing)

```bash
# macOS
brew install --cask docker

# Ubuntu — see Section 5 for server install
```

---

## 2. SSH Key Setup for Passwordless Login

Before deploying to a remote server, set up SSH key authentication so you don't need to type a password every time.

### Generate a key pair (if you don't have one)

```bash
# Check if you already have a key
ls ~/.ssh/id_ed25519.pub 2>/dev/null && echo "Key exists" || echo "No key found"

# Generate a new Ed25519 key (recommended)
ssh-keygen -t ed25519 -C "your-email@example.com"
# Press Enter for default path (~/.ssh/id_ed25519)
# Press Enter twice for no passphrase (or set one for extra security)
```

### Copy the key to your remote server

```bash
# Replace USER and SERVER_IP with your values
ssh-copy-id USER@SERVER_IP

# Example:
ssh-copy-id claude@10.0.0.92
```

If `ssh-copy-id` is not available (some macOS versions):

```bash
cat ~/.ssh/id_ed25519.pub | ssh USER@SERVER_IP "mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys"
```

### Test passwordless login

```bash
ssh USER@SERVER_IP
# Should log in without asking for a password
```

### Create a dedicated deploy user (recommended)

On the remote server, create a user specifically for deployments:

```bash
# SSH into the server with your current user (or root)
ssh root@SERVER_IP

# Create the user
sudo adduser claude
# Set a strong password (you won't need it after SSH key setup)

# Give Docker access
sudo usermod -aG docker claude

# Allow sudo without password (optional, for Docker builds)
echo "claude ALL=(ALL) NOPASSWD: ALL" | sudo tee /etc/sudoers.d/claude

# Exit and copy your SSH key to the new user
exit
ssh-copy-id claude@SERVER_IP

# Test
ssh claude@SERVER_IP
```

---

## 3. Clone the Project

### From GitHub

```bash
# Using GitHub CLI (recommended)
gh repo clone smilianov/MikroTik-NetMap
cd MikroTik-NetMap

# Or using git directly
git clone git@github.com:smilianov/MikroTik-NetMap.git
cd MikroTik-NetMap
```

### Initial local setup

```bash
# Copy example configs
cp config/netmap.example.yaml config/netmap.yaml
cp .env.example .env

# Backend dependencies (for local development)
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt

# Frontend dependencies (for local development)
cd frontend && npm install && cd ..
```

### Pull latest changes

```bash
cd MikroTik-NetMap
git pull origin main
```

---

## 4. Working with Claude Code

Claude Code is an AI-powered CLI that can help you develop, debug, and deploy this project.

### Install Claude Code

```bash
# Install globally via npm
npm install -g @anthropic-ai/claude-code

# Verify installation
claude --version
```

### Open the project in Claude Code

```bash
cd MikroTik-NetMap
claude
```

Claude Code will automatically read the project's `CLAUDE.md` file (if present) and understand the project structure.

### Add the project to Claude Code

If this is a new project or you want Claude to remember project-specific context, create a `CLAUDE.md` in the project root:

```bash
# Claude Code can create this for you
claude
# Then type: /init
```

Or manually create `CLAUDE.md`:

```markdown
# MikroTik-NetMap

## Project Overview
Real-time MikroTik network topology dashboard (FastAPI + React 19 + vis-network).

## Tech Stack
- Backend: Python 3.13 + FastAPI
- Frontend: React 19 + TypeScript + Vite + Zustand
- Graph: vis-network
- Deploy: Docker

## Key Commands
- Backend dev: `cd backend && python -m uvicorn main:app --host 0.0.0.0 --port 8585 --reload`
- Frontend dev: `cd frontend && npm run dev`
- Build: `cd frontend && npm run build`
- Docker: `docker build -t mikrotik-netmap . && docker run -d --name netmap --network host -v $(pwd)/config:/app/config mikrotik-netmap`

## Remote Server
- Server: 10.0.0.92, SSH user: claude
- Deploy: rsync source → docker build → docker run
```

### Common Claude Code workflows

```bash
# Start Claude Code in the project
cd MikroTik-NetMap
claude

# Example prompts:
# "Add a new device type called 'firewall' with a shield icon"
# "Fix the WebSocket reconnect loop when auth expires"
# "Deploy the latest changes to 10.0.0.92"
# "Run the frontend build and check for errors"
```

### Using Claude Code from VS Code

1. Install the **Claude Code** extension from the VS Code marketplace
2. Open the `MikroTik-NetMap` folder in VS Code
3. Open the Claude Code panel (sidebar or Ctrl+Shift+P → "Claude Code")
4. Claude has full access to your project files and terminal

---

## 5. Prepare the Remote Server (Ubuntu 24.04)

Starting from a fresh Ubuntu Server 24.04 installation.

### 5.1 Connect to the server

```bash
ssh root@SERVER_IP
# Or ssh YOUR_USER@SERVER_IP if root login is disabled
```

### 5.2 Update the system

```bash
sudo apt update && sudo apt upgrade -y
```

### 5.3 Install Docker

```bash
# Install Docker using the official convenience script
curl -fsSL https://get.docker.com | sudo sh

# Add your user to the docker group (so you don't need sudo for docker commands)
sudo usermod -aG docker $USER

# Apply group changes (or log out and back in)
newgrp docker

# Verify Docker is running
docker --version
docker run hello-world
```

### 5.4 Install useful tools

```bash
sudo apt install -y rsync curl git
```

### 5.5 Configure firewall (if enabled)

```bash
# Allow SSH
sudo ufw allow 22/tcp

# Allow NetMap web UI
sudo ufw allow 8585/tcp

# Allow Grafana (if running on same server for auth)
sudo ufw allow 3000/tcp

# Enable firewall
sudo ufw enable
sudo ufw status
```

### 5.6 Create the project directory

```bash
sudo mkdir -p /opt/MikroTik-NetMap
sudo chown $USER:$USER /opt/MikroTik-NetMap
```

---

## 6. Deploy to the Remote Server

Run these commands from your **local machine** (where you cloned the repo).

### 6.1 Sync the project files

```bash
# From your local project directory
cd MikroTik-NetMap

rsync -avz \
  --exclude='node_modules/' \
  --exclude='.venv/' \
  --exclude='__pycache__/' \
  --exclude='frontend/dist/' \
  --exclude='.git/' \
  --exclude='.DS_Store' \
  . claude@SERVER_IP:/opt/MikroTik-NetMap/
```

### 6.2 Create the production config

```bash
ssh claude@SERVER_IP

cd /opt/MikroTik-NetMap

# Copy the example config
cp config/netmap.example.yaml config/netmap.yaml

# Edit the config with your real devices
nano config/netmap.yaml
```

See [Section 7](#7-configure-the-application) for configuration details.

### 6.3 Build the Docker image

```bash
# On the remote server
cd /opt/MikroTik-NetMap
docker build -t mikrotik-netmap:latest .
```

This takes 1-2 minutes. The Dockerfile runs a multi-stage build:
1. **Stage 1** (Node 22 Alpine): builds the React frontend
2. **Stage 2** (Python 3.13 Slim): installs backend dependencies, copies built frontend

### 6.4 Run the container

```bash
docker run -d \
  --name netmap \
  --network host \
  -v /opt/MikroTik-NetMap/config:/app/config \
  --restart unless-stopped \
  mikrotik-netmap:latest
```

**Flags explained:**
- `--network host` — container shares the host network (needed for Grafana auth on same host, and direct access to MikroTik devices)
- `-v .../config:/app/config` — mounts the config directory so you can edit `netmap.yaml` without rebuilding the image
- `--restart unless-stopped` — auto-start on boot

### 6.5 Verify it's running

```bash
# Check container status
docker ps

# Check logs
docker logs netmap --tail 20

# Test the API
curl http://localhost:8585/api/health
```

### 6.6 Access the dashboard

Open in your browser: **http://SERVER_IP:8585**

---

## 7. Configure the Application

Edit `/opt/MikroTik-NetMap/config/netmap.yaml` on the server.

### Minimal production config

```yaml
server:
  host: 0.0.0.0
  port: 8585

ping:
  interval: 2
  timeout: 1

api_defaults:
  username: prometheus        # RouterOS API username
  password: "YourPassword"    # RouterOS API password
  api_type: classic           # "classic" (port 8728) or "rest" (port 443)
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
  protocols: [mndp, lldp]
  auto_add_devices: true
  auto_add_links: true

traffic:
  enabled: true
  interval: 10
```

### Enable authentication (optional)

Requires a Grafana instance running on the same server (or network-accessible).

```yaml
auth:
  enabled: true
  grafana_url: "http://localhost:3000"
  session_ttl: 28800    # 8 hours
```

### Apply config changes

After editing the config, restart the container:

```bash
docker restart netmap
```

No rebuild needed — the config directory is volume-mounted.

For a full configuration reference, see [CONFIGURATION.md](CONFIGURATION.md).

---

## 8. Verify the Deployment

### Health check

```bash
curl -s http://SERVER_IP:8585/api/health | python3 -m json.tool
```

Expected output:
```json
{
    "status": "ok",
    "version": "0.4.0-beta",
    "devices": 1,
    "ws_clients": 0,
    "ping_running": true,
    "discovery_running": true,
    "traffic_running": true,
    "discovered_devices": 0,
    "discovered_links": 0,
    "auth_enabled": false,
    "active_sessions": 0
}
```

### Check logs

```bash
# View recent logs
docker logs netmap --tail 50

# Follow logs in real-time
docker logs netmap -f
```

### Common log messages

| Message | Meaning |
|---------|---------|
| `MikroTik-NetMap started on 0.0.0.0:8585` | App is running |
| `Auth enabled: Grafana at http://localhost:3000` | Authentication is active |
| `TopologyDiscovery enabled: N devices` | Discovery is running |
| `Discovery sweep: X half-links, Y full links` | Discovery found neighbours |
| `Login: user=admin role=Admin` | Successful login |
| `RouterOsApiConnectionError: timed out` | Device unreachable via API (ping still works) |

---

## 9. Update an Existing Deployment

When you make code changes locally and want to deploy them:

### Quick update (from local machine)

```bash
# 1. Sync source files (exclude config to preserve production settings)
rsync -avz \
  --exclude='node_modules/' --exclude='.venv/' --exclude='__pycache__/' \
  --exclude='frontend/dist/' --exclude='.git/' --exclude='config/' \
  --exclude='.DS_Store' \
  . claude@SERVER_IP:/opt/MikroTik-NetMap/

# 2. Rebuild and restart (on server)
ssh claude@SERVER_IP "cd /opt/MikroTik-NetMap && \
  docker build -t mikrotik-netmap:latest . && \
  docker stop netmap && docker rm netmap && \
  docker run -d --name netmap --network host \
    -v /opt/MikroTik-NetMap/config:/app/config \
    --restart unless-stopped mikrotik-netmap:latest"
```

### One-liner deploy

Add this to your `~/.zshrc` or `~/.bashrc` for convenience:

```bash
alias netmap-deploy='cd ~/MikroTik-NetMap && \
  rsync -avz --exclude="node_modules/" --exclude=".venv/" --exclude="__pycache__/" \
    --exclude="frontend/dist/" --exclude=".git/" --exclude="config/" --exclude=".DS_Store" \
    . claude@SERVER_IP:/opt/MikroTik-NetMap/ && \
  ssh claude@SERVER_IP "cd /opt/MikroTik-NetMap && \
    docker build -t mikrotik-netmap:latest . && \
    docker stop netmap && docker rm netmap && \
    docker run -d --name netmap --network host \
      -v /opt/MikroTik-NetMap/config:/app/config \
      --restart unless-stopped mikrotik-netmap:latest"'
```

Then just run: `netmap-deploy`

---

## 10. Troubleshooting

### Can't SSH to server (permission denied)

```bash
# Check your key is loaded
ssh-add -l

# If empty, add your key
ssh-add ~/.ssh/id_ed25519

# Verify the public key is on the server
ssh USER@SERVER_IP "cat ~/.ssh/authorized_keys"
```

### Docker permission denied

```bash
# Add your user to the docker group
sudo usermod -aG docker $USER

# Log out and back in, or run:
newgrp docker
```

### Container won't start

```bash
# Check if port 8585 is already in use
ss -tlnp | grep 8585

# Check container logs
docker logs netmap

# Remove old container and try again
docker rm -f netmap
docker run -d --name netmap --network host \
  -v /opt/MikroTik-NetMap/config:/app/config \
  mikrotik-netmap:latest
```

### Devices show as DOWN

- **ICMP blocked:** Ensure the server can ping MikroTik devices: `ping 10.0.0.1`
- **Firewall:** Check MikroTik firewall rules allow ICMP from the server IP
- **Docker networking:** With `--network host`, the container uses the host's network stack. Verify the host can reach the devices.

### Discovery not finding devices

- Ensure `api_defaults.password` is set correctly
- Verify API access: `curl -k -u prometheus:YourPassword https://10.0.0.1/rest/ip/neighbor` (REST) or test Classic API on port 8728
- Check that the MikroTik API service is enabled: `/ip/service/set api disabled=no` (Classic) or `/ip/service/set www-ssl disabled=no` (REST)

### Auth login fails ("Invalid credentials")

- Test Grafana directly: `curl -u admin:admin http://localhost:3000/api/user`
- If using `--network host`, `localhost:3000` should work. If using `-p 8585:8585`, use the server's IP or Docker network IP instead.
- Reset Grafana admin password: `docker exec GRAFANA_CONTAINER grafana-cli admin reset-admin-password admin`

### Browser shows old version after update

- Hard refresh: **Cmd+Shift+R** (Mac) or **Ctrl+Shift+R** (Windows/Linux)
- Or Shift+click the browser's refresh button
- Clear browser cache if still stale

---

## Complete Example: Fresh Ubuntu 24.04 to Running Dashboard

Here's the entire process end-to-end, assuming you have a fresh Ubuntu 24.04 server at `10.0.0.92`:

```bash
# === ON YOUR LOCAL MACHINE ===

# 1. Generate SSH key (skip if you already have one)
ssh-keygen -t ed25519 -C "your-email@example.com"

# 2. Copy key to server (enter password when prompted — last time you'll need it)
ssh-copy-id root@10.0.0.92

# 3. SSH in and prepare the server
ssh root@10.0.0.92

# 4. Create deploy user
adduser claude
usermod -aG docker claude 2>/dev/null  # docker group may not exist yet
echo "claude ALL=(ALL) NOPASSWD: ALL" | tee /etc/sudoers.d/claude
exit

# 5. Copy SSH key to deploy user
ssh-copy-id claude@10.0.0.92

# 6. Install Docker on the server
ssh claude@10.0.0.92 "curl -fsSL https://get.docker.com | sudo sh && sudo usermod -aG docker claude"

# 7. Clone the project locally (if not already done)
gh repo clone smilianov/MikroTik-NetMap
cd MikroTik-NetMap

# 8. Sync to server
rsync -avz \
  --exclude='node_modules/' --exclude='.venv/' --exclude='__pycache__/' \
  --exclude='frontend/dist/' --exclude='.git/' --exclude='.DS_Store' \
  . claude@10.0.0.92:/opt/MikroTik-NetMap/

# 9. SSH in and configure
ssh claude@10.0.0.92
cd /opt/MikroTik-NetMap
cp config/netmap.example.yaml config/netmap.yaml
nano config/netmap.yaml
# Add your MikroTik devices, enable discovery, set API credentials

# 10. Build and run
docker build -t mikrotik-netmap:latest .
docker run -d --name netmap --network host \
  -v /opt/MikroTik-NetMap/config:/app/config \
  --restart unless-stopped \
  mikrotik-netmap:latest

# 11. Verify
curl http://localhost:8585/api/health
```

Open **http://10.0.0.92:8585** in your browser. Done!
