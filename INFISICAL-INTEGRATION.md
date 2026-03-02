# 🗺️ MikroTik-NetMap — Infisical Integration

> **2-3 Hour Quick Win**: Migrate network mapping credentials to centralized secrets management
>
> **Application**: Full-stack network discovery & visualization for MikroTik devices

## 🎯 Integration Benefits

**BEFORE** (File-based secrets):
```bash
# Manual .env file management
cp .env.example .env
vim .env  # Edit device passwords
docker-compose up -d
```

**AFTER** (Infisical secrets):
```bash
# Centralized credential management
export INFISICAL_TOKEN=<token>
./scripts/infisical-sync.sh --generate-env
docker-compose up -d  # Automatic secret injection
```

### Security Improvements
- ✅ **Centralized network device credentials** for all RouterOS devices
- ✅ **Audit logging** for all secret access and network discovery
- ✅ **Environment isolation** (staging vs production networks)
- ✅ **Secret rotation** without application restarts
- ✅ **Docker integration** with automatic .env generation

---

## 🚀 Quick Setup (30 Minutes)

### Step 1: Setup Infisical Authentication (5 min)

```bash
cd MikroTik-NetMap/
./scripts/infisical-sync.sh --setup
```

Follow prompts to:
1. Access Infisical web UI
2. Create `mikrotik-netmap` project
3. Generate service token
4. Test authentication

### Step 2: Migrate Existing Credentials (10 min)

```bash
# If you have .env file, migrate automatically
./scripts/infisical-sync.sh --migrate

# Add secrets manually in Infisical web UI:
# Project: mikrotik-netmap
# Environment: production
```

**Required Secrets:**

| Secret Name | Example Value | Description |
|-------------|---------------|-------------|
| `NETMAP_PORT` | `8585` | Application port |
| `CORE_ROUTER_PASS` | `<secure-password>` | Core router password |
| `SWITCH_PASS` | `<secure-password>` | Switch password |
| `BRANCH_PASS` | `<secure-password>` | Branch device password |
| `ROUTER_PASS` | `<secure-password>` | Generic router password (used in netmap.yaml) |

**Optional Secrets:**

| Secret Name | Example Value | Description |
|-------------|---------------|-------------|
| `SNMP_COMMUNITY` | `public` | SNMP community string |
| `SLACK_WEBHOOK_URL` | `https://hooks.slack.com/...` | Slack notifications |
| `TELEGRAM_BOT_TOKEN` | `123456:ABC-DEF...` | Telegram bot token |
| `TELEGRAM_CHAT_ID` | `-1001234567890` | Telegram chat ID |

### Step 3: Update Configuration (10 min)

```bash
# Update netmap.yaml for Infisical integration
./scripts/infisical-sync.sh --update-config

# Create enhanced Docker Compose example
./scripts/infisical-sync.sh --create-docker-example
```

### Step 4: Test Integration (5 min)

```bash
# Verify all secrets accessible
./scripts/infisical-sync.sh --verify

# Test Docker integration
./scripts/infisical-sync.sh --docker

# Test device connections
./scripts/infisical-sync.sh --test
```

---

## 🔧 Usage Examples

### Network Discovery (Enhanced)
```bash
# Generate environment from Infisical
./scripts/infisical-sync.sh --generate-env

# Start with Infisical-managed credentials
docker-compose up -d

# Access NetMap with secure credentials
open http://localhost:8585
```

### Production Deployment
```bash
# Use enhanced Docker Compose with Infisical
docker-compose -f docker-compose.infisical.yml up -d

# Monitor with centralized credentials
docker-compose -f docker-compose.infisical.yml logs -f netmap
```

### Multi-Environment Management
```bash
# Staging environment
export ENVIRONMENT=staging
./scripts/infisical-sync.sh --generate-env
docker-compose up -d

# Production environment
export ENVIRONMENT=production
./scripts/infisical-sync.sh --generate-env
docker-compose -f docker-compose.infisical.yml up -d
```

---

## 🔄 Configuration Integration

### netmap.yaml (Automatic Infisical Integration)
```yaml
server:
  host: 0.0.0.0
  port: ${NETMAP_PORT:-8585}  # From Infisical

api_defaults:
  username: prometheus
  password: "${ROUTER_PASS}"  # From Infisical
  api_type: classic
  port: 8728

discovery:
  enabled: true
  interval: 300
  protocols: [mndp, lldp]
  auto_add_devices: false
  auto_add_links: false
```

### Device-Specific Passwords
```yaml
devices:
  - name: Core-Router
    host: 10.0.0.1
    password: "${CORE_ROUTER_PASS}"  # From Infisical

  - name: Main-Switch
    host: 10.0.0.2
    password: "${SWITCH_PASS}"       # From Infisical

  - name: Branch-Device
    host: 10.0.1.1
    password: "${BRANCH_PASS}"       # From Infisical
```

---

## 🐳 Docker Integration

### Enhanced Production Setup
```yaml
# docker-compose.infisical.yml
services:
  netmap:
    build: .
    container_name: mikrotik-netmap-infisical
    restart: unless-stopped
    ports:
      - "${NETMAP_PORT:-8585}:8585"
    env_file:
      - .env  # Generated from Infisical
    deploy:
      resources:
        limits:
          cpus: "2.0"
          memory: 1G
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8585/api/health"]
```

### Development vs Production
```bash
# Development (simple)
./scripts/infisical-sync.sh --generate-env
docker-compose up -d

# Production (enhanced)
./scripts/infisical-sync.sh --generate-env
docker-compose -f docker-compose.infisical.yml up -d
```

---

## 📈 Network Monitoring Integration

### Real-time Discovery
```bash
# Monitor device discovery with Infisical credentials
./scripts/infisical-sync.sh --test

# Check application logs
docker-compose logs -f netmap | grep -E "(discovered|connected|error)"
```

### API Access with Secure Credentials
```bash
# All API endpoints use Infisical-managed credentials
curl http://localhost:8585/api/devices
curl http://localhost:8585/api/topology
curl http://localhost:8585/api/health
```

Expected output:
```json
{
  "status": "healthy",
  "devices_discovered": 15,
  "last_discovery": "2026-03-02T10:15:30Z",
  "credential_source": "infisical"
}
```

---

## 🛡️ Security Features

### Secret Rotation
```bash
# Update any device password in Infisical web UI
# Then regenerate environment file
./scripts/infisical-sync.sh --generate-env

# Restart application with new credentials
docker-compose restart netmap
```

### Environment Isolation
```bash
# Different device credentials per environment
export ENVIRONMENT=staging
./scripts/infisical-sync.sh --verify  # Uses staging secrets

export ENVIRONMENT=production
./scripts/infisical-sync.sh --verify  # Uses production secrets
```

### Audit Logging
- All secret access logged in Infisical
- Track which discovery sessions accessed which credentials
- Monitor for unauthorized device access attempts

---

## 🚨 Rollback Plan

If Infisical integration causes issues:

```bash
# 1. Restore original .env file (instant)
cp .env.backup .env
docker-compose restart netmap

# 2. Use original Docker Compose (fallback)
docker-compose -f docker-compose.yml up -d

# 3. Remove Infisical integration (if needed)
rm -f .env.infisical
rm -f docker-compose.infisical.yml
```

**Recovery Time**: < 2 minutes
**Data Loss**: None (all device configurations preserved)

---

## 📊 Integration Summary

### Files Added/Modified:
- ✅ `scripts/infisical-sync.sh` — Complete integration automation (517 lines)
- ✅ `docker-compose.infisical.yml` — Enhanced production deployment
- ✅ `config/netmap.yaml` — Updated for environment variable integration
- ✅ `.env` — Generated from Infisical (replaces manual editing)

### Network Impact:
- 🔒 **Zero downtime** — application continues running during migration
- 🔒 **Zero discovery changes** — same RouterOS API calls, secure credentials
- 🔒 **Enhanced security** — centralized device credential management
- 🔒 **Improved monitoring** — secret access logging and audit trails

### Next Steps:
- [ ] Deploy to production network discovery
- [ ] Integrate with network monitoring alerts
- [ ] Add automated device credential rotation
- [ ] Extend to additional RouterOS device types

**Time Investment**: 30 minutes setup + 2-3 hours total integration
**ROI**: Immediate security improvement + foundation for network automation scaling

---

## 🌐 Network Architecture

### Integration Topology
```
┌─────────────────────────────────────────────┐
│            Infisical Server                  │
│         (Centralized Secrets)               │
└─────────────────┬───────────────────────────┘
                  │
    ┌─────────────▼──────────────┐
    │      MikroTik-NetMap       │
    │    (Docker Container)      │
    │                            │
    │  ├─ Network Discovery      │
    │  ├─ Device Visualization   │
    │  └─ API Endpoints          │
    └─────────────┬──────────────┘
                  │
         RouterOS API (8728)
                  │
    ┌─────────────▼──────────────┐
    │      Network Devices       │
    │                            │
    │  ├─ Core Router           │
    │  ├─ Switches              │
    │  ├─ Branch Devices        │
    │  └─ Access Points         │
    └────────────────────────────┘
```

**Credential Flow:**
1. Infisical stores device passwords securely
2. NetMap retrieves credentials at startup
3. Discovery engine connects to RouterOS devices
4. Network topology updated in real-time
5. All access logged for audit compliance