#!/usr/bin/env bash
###############################################################################
# MikroTik-NetMap — Infisical Integration Script
#
# Integrates MikroTik network mapping application with Infisical secrets management.
# Replaces .env file approach with centralized credential management for
# network device discovery and visualization.
#
# Usage:
#   ./scripts/infisical-sync.sh --setup       # Initial setup
#   ./scripts/infisical-sync.sh --verify      # Verify integration
#   ./scripts/infisical-sync.sh --test        # Test device connections
#   ./scripts/infisical-sync.sh --migrate     # Migrate from .env
#   ./scripts/infisical-sync.sh --docker      # Test Docker integration
###############################################################################

set -euo pipefail

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
INFISICAL_PROJECT="mikrotik-netmap"
ENVIRONMENT="${ENVIRONMENT:-production}"
INFISICAL_URL="${INFISICAL_URL:-https://infisical.internal.company.local}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log() { echo -e "${BLUE}[$(date '+%H:%M:%S')]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*" >&2; }
warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
success() { echo -e "${GREEN}[SUCCESS]${NC} $*"; }

# Check prerequisites
check_prerequisites() {
    log "Checking prerequisites for MikroTik-NetMap..."

    if ! command -v infisical >/dev/null 2>&1; then
        error "Infisical CLI not installed"
        echo "Install: curl -1sLf 'https://dl.cloudsmith.io/public/infisical/infisical-cli/setup.deb.sh' | sudo -E bash && sudo apt-get install infisical"
        exit 1
    fi

    if ! command -v docker >/dev/null 2>&1; then
        error "Docker not installed"
        echo "Install Docker: https://docs.docker.com/get-docker/"
        exit 1
    fi

    if ! command -v docker-compose >/dev/null 2>&1; then
        error "Docker Compose not installed"
        echo "Install Docker Compose: https://docs.docker.com/compose/install/"
        exit 1
    fi

    success "Prerequisites satisfied"
}

# Setup Infisical authentication
setup_authentication() {
    log "Setting up Infisical authentication for MikroTik-NetMap..."

    echo "MikroTik-NetMap — Network Discovery & Visualization"
    echo "Project: ${INFISICAL_PROJECT}"
    echo "Environment: ${ENVIRONMENT}"
    echo
    echo "Steps:"
    echo "1. Login to: ${INFISICAL_URL}"
    echo "2. Create project: ${INFISICAL_PROJECT}"
    echo "3. Add environment: ${ENVIRONMENT}"
    echo "4. Generate service token"
    echo

    read -p "Enter Infisical service token: " -s INFISICAL_TOKEN
    echo

    # Test authentication
    if ! INFISICAL_TOKEN="$INFISICAL_TOKEN" infisical export --env="$ENVIRONMENT" >/dev/null 2>&1; then
        error "Authentication failed. Check token and project access."
        exit 1
    fi

    # Store token
    echo "INFISICAL_TOKEN=$INFISICAL_TOKEN" > "$PROJECT_ROOT/.env.infisical"
    chmod 600 "$PROJECT_ROOT/.env.infisical"

    success "Authentication configured"
}

# Migrate from .env file
migrate_from_env() {
    log "Migrating network device credentials from .env to Infisical..."

    local env_file="$PROJECT_ROOT/.env"
    if [[ ! -f "$env_file" ]]; then
        warn "No .env file found. You'll need to add secrets manually to Infisical."
        echo
        echo "Required secrets for MikroTik-NetMap:"
        echo "  NETMAP_PORT         - Application port (default: 8585)"
        echo "  CORE_ROUTER_PASS    - Core router password"
        echo "  SWITCH_PASS         - Switch password"
        echo "  BRANCH_PASS         - Branch device password"
        echo "  ROUTER_PASS         - Generic router password (used in netmap.yaml)"
        echo
        echo "Optional secrets:"
        echo "  SNMP_COMMUNITY      - SNMP community string"
        echo "  SLACK_WEBHOOK_URL   - Slack notifications"
        echo "  TELEGRAM_BOT_TOKEN  - Telegram notifications"
        echo "  TELEGRAM_CHAT_ID    - Telegram chat ID"
        return 0
    fi

    # Source the .env file
    set -a
    source "$env_file"
    set +a

    # Prepare secrets for Infisical
    declare -A secrets=(
        ["NETMAP_PORT"]="${NETMAP_PORT:-8585}"
        ["CORE_ROUTER_PASS"]="${CORE_ROUTER_PASS:-}"
        ["SWITCH_PASS"]="${SWITCH_PASS:-}"
        ["BRANCH_PASS"]="${BRANCH_PASS:-}"
        ["ROUTER_PASS"]="${ROUTER_PASS:-${CORE_ROUTER_PASS:-}}"
        ["SNMP_COMMUNITY"]="${SNMP_COMMUNITY:-}"
        ["SLACK_WEBHOOK_URL"]="${SLACK_WEBHOOK_URL:-}"
        ["TELEGRAM_BOT_TOKEN"]="${TELEGRAM_BOT_TOKEN:-}"
        ["TELEGRAM_CHAT_ID"]="${TELEGRAM_CHAT_ID:-}"
    )

    echo "Secrets to migrate:"
    for key in "${!secrets[@]}"; do
        local value="${secrets[$key]}"
        if [[ -n "$value" ]]; then
            if [[ "$key" == "NETMAP_PORT" ]]; then
                echo "  ✓ $key = $value"
            else
                echo "  ✓ $key = ${value:0:8}..."
            fi
        else
            echo "  ⚠ $key = (empty/optional)"
        fi
    done

    read -p "Proceed with migration? [y/N]: " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        warn "Migration cancelled"
        return 0
    fi

    # Add secrets to Infisical
    for key in "${!secrets[@]}"; do
        local value="${secrets[$key]}"
        if [[ -n "$value" ]]; then
            if infisical secrets set "$key" "$value" --env="$ENVIRONMENT" >/dev/null 2>&1; then
                success "Migrated: $key"
            else
                error "Failed to migrate: $key"
            fi
        else
            warn "Skipped empty: $key"
        fi
    done

    # Backup original .env
    cp "$env_file" "$env_file.backup"
    success "Original .env backed up to .env.backup"
}

# Generate .env file from Infisical
generate_env_file() {
    log "Generating .env file from Infisical..."

    # Load token
    if [[ -f "$PROJECT_ROOT/.env.infisical" ]]; then
        source "$PROJECT_ROOT/.env.infisical"
        export INFISICAL_TOKEN
    fi

    if [[ -z "${INFISICAL_TOKEN:-}" ]]; then
        error "INFISICAL_TOKEN not found. Run: $0 --setup"
        exit 1
    fi

    # Backup existing .env file before overwriting
    if [[ -f "$PROJECT_ROOT/.env" ]]; then
        cp "$PROJECT_ROOT/.env" "$PROJECT_ROOT/.env.infisical.backup"
        log "Existing .env backed up to .env.infisical.backup"
    fi

    # Generate .env from Infisical
    infisical export --env="$ENVIRONMENT" --format=dotenv > "$PROJECT_ROOT/.env.tmp"

    # Add header and format
    {
        echo "# Generated from Infisical on $(date)"
        echo "# Project: ${INFISICAL_PROJECT}"
        echo "# Environment: ${ENVIRONMENT}"
        echo "#"
        echo "# MikroTik-NetMap — Network Discovery & Visualization"
        echo "# This file is auto-generated. Edit secrets in Infisical web UI."
        echo ""
        echo "# Application configuration"
        grep "^NETMAP_PORT=" "$PROJECT_ROOT/.env.tmp" || echo "NETMAP_PORT=8585"
        echo ""
        echo "# Device passwords (referenced in netmap.yaml as \${VAR})"
        grep "^CORE_ROUTER_PASS=" "$PROJECT_ROOT/.env.tmp" || echo "CORE_ROUTER_PASS="
        grep "^SWITCH_PASS=" "$PROJECT_ROOT/.env.tmp" || echo "SWITCH_PASS="
        grep "^BRANCH_PASS=" "$PROJECT_ROOT/.env.tmp" || echo "BRANCH_PASS="
        grep "^ROUTER_PASS=" "$PROJECT_ROOT/.env.tmp" || echo "ROUTER_PASS="
        echo ""
        echo "# Optional: SNMP community string"
        if grep -q "^SNMP_COMMUNITY=" "$PROJECT_ROOT/.env.tmp"; then
            grep "^SNMP_COMMUNITY=" "$PROJECT_ROOT/.env.tmp"
        else
            echo "# SNMP_COMMUNITY=public"
        fi
        echo ""
        echo "# Optional: Notification integrations"
        if grep -q "^SLACK_WEBHOOK_URL=" "$PROJECT_ROOT/.env.tmp"; then
            grep "^SLACK_WEBHOOK_URL=" "$PROJECT_ROOT/.env.tmp"
        else
            echo "# SLACK_WEBHOOK_URL=https://hooks.slack.com/services/..."
        fi
        if grep -q "^TELEGRAM_BOT_TOKEN=" "$PROJECT_ROOT/.env.tmp"; then
            grep "^TELEGRAM_BOT_TOKEN=" "$PROJECT_ROOT/.env.tmp"
            grep "^TELEGRAM_CHAT_ID=" "$PROJECT_ROOT/.env.tmp" || echo "# TELEGRAM_CHAT_ID=-1001234567890"
        else
            echo "# TELEGRAM_BOT_TOKEN=123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"
            echo "# TELEGRAM_CHAT_ID=-1001234567890"
        fi
    } > "$PROJECT_ROOT/.env"

    rm -f "$PROJECT_ROOT/.env.tmp"

    success "Generated .env file from Infisical"
    log "File location: $PROJECT_ROOT/.env"
}

# Verify Infisical integration
verify_integration() {
    log "Verifying Infisical integration..."

    # Load token
    if [[ -f "$PROJECT_ROOT/.env.infisical" ]]; then
        source "$PROJECT_ROOT/.env.infisical"
        export INFISICAL_TOKEN
    fi

    if [[ -z "${INFISICAL_TOKEN:-}" ]]; then
        error "INFISICAL_TOKEN not found. Run: $0 --setup"
        exit 1
    fi

    echo "=== MikroTik-NetMap Infisical Integration Verification ==="

    echo "✅ INFISICAL_TOKEN configured"
    echo "✅ Project: ${INFISICAL_PROJECT}"
    echo "✅ Environment: ${ENVIRONMENT}"

    # Test required secrets
    local required_secrets=("NETMAP_PORT" "CORE_ROUTER_PASS" "SWITCH_PASS" "BRANCH_PASS" "ROUTER_PASS")
    local optional_secrets=("SNMP_COMMUNITY" "SLACK_WEBHOOK_URL" "TELEGRAM_BOT_TOKEN" "TELEGRAM_CHAT_ID")
    local failed_secrets=()

    echo
    echo "Required secrets:"
    for secret in "${required_secrets[@]}"; do
        if infisical secrets get "$secret" --env="$ENVIRONMENT" --plain >/dev/null 2>&1; then
            echo "✅ $secret"
        else
            echo "❌ $secret"
            failed_secrets+=("$secret")
        fi
    done

    echo
    echo "Optional secrets:"
    for secret in "${optional_secrets[@]}"; do
        if infisical secrets get "$secret" --env="$ENVIRONMENT" --plain >/dev/null 2>&1; then
            echo "✅ $secret"
        else
            echo "⚠️  $secret (optional)"
        fi
    done

    if [[ ${#failed_secrets[@]} -eq 0 ]]; then
        echo
        success "All required secrets accessible via Infisical!"
        return 0
    else
        echo
        error "Missing required secrets: ${failed_secrets[*]}"
        echo "Add them to Infisical:"
        echo "   Project: ${INFISICAL_PROJECT}"
        echo "   Environment: ${ENVIRONMENT}"
        return 1
    fi
}

# Test Docker integration
test_docker_integration() {
    log "Testing Docker integration..."

    # Load token and generate .env
    if [[ -f "$PROJECT_ROOT/.env.infisical" ]]; then
        source "$PROJECT_ROOT/.env.infisical"
        export INFISICAL_TOKEN
    fi

    generate_env_file

    cd "$PROJECT_ROOT"

    # Test Docker Compose configuration
    log "Testing Docker Compose config..."
    if docker-compose config >/dev/null 2>&1; then
        success "Docker Compose configuration valid"
    else
        error "Docker Compose configuration invalid"
        return 1
    fi

    # Test container build
    log "Building Docker container..."
    if docker-compose build >/dev/null 2>&1; then
        success "Docker container built successfully"
    else
        error "Docker container build failed"
        return 1
    fi

    # Test environment variable injection
    log "Testing environment variable injection..."
    local test_output
    test_output=$(docker-compose run --rm netmap printenv | grep -E "^(NETMAP_|CORE_|SWITCH_|BRANCH_|ROUTER_)" || true)

    if [[ -n "$test_output" ]]; then
        success "Environment variables injected successfully:"
        echo "$test_output" | while read -r line; do
            local var_name="${line%%=*}"
            echo "   ✓ $var_name"
        done
    else
        error "Environment variables not injected"
        return 1
    fi

    success "Docker integration test completed"
}

# Test network device connections
test_device_connections() {
    log "Testing network device connections with Infisical credentials..."

    # Load token and generate .env
    if [[ -f "$PROJECT_ROOT/.env.infisical" ]]; then
        source "$PROJECT_ROOT/.env.infisical"
        export INFISICAL_TOKEN
    fi

    generate_env_file

    cd "$PROJECT_ROOT"

    log "Starting NetMap application for connection testing..."

    # Start the application in detached mode
    if docker-compose up -d >/dev/null 2>&1; then
        success "NetMap application started"

        # Wait for application startup
        sleep 10

        # Test application health
        local netmap_port
        netmap_port=$(grep "^NETMAP_PORT=" .env | cut -d'=' -f2 || echo "8585")

        if curl -s "http://localhost:${netmap_port}/api/devices" >/dev/null 2>&1; then
            success "NetMap API responding on port ${netmap_port}"
        else
            warn "NetMap API not responding (this is normal if no devices configured yet)"
        fi

        # Check container logs for errors
        log "Checking container logs..."
        local log_output
        log_output=$(docker-compose logs --tail=20 netmap 2>&1 | grep -i error || true)

        if [[ -z "$log_output" ]]; then
            success "No errors detected in container logs"
        else
            warn "Some errors detected (check if device connections are configured):"
            echo "$log_output" | head -5
        fi

        # Stop the test instance
        docker-compose down >/dev/null 2>&1
        success "Test instance stopped"
    else
        error "Failed to start NetMap application"
        return 1
    fi

    success "Device connection test completed"
}

# Update netmap.yaml configuration
update_netmap_config() {
    log "Updating netmap.yaml for enhanced Infisical integration..."

    local config_file="$PROJECT_ROOT/config/netmap.yaml"
    local example_file="$PROJECT_ROOT/config/netmap.example.yaml"

    # Idempotency guard: check if config already has Infisical integration
    if [[ -f "$config_file" ]]; then
        if grep -q "NETMAP_PORT.*:-" "$config_file" && grep -q "ROUTER_PASS" "$config_file"; then
            success "netmap.yaml already configured with Infisical integration"
            return 0
        fi
    fi

    if [[ ! -f "$config_file" && -f "$example_file" ]]; then
        log "Creating netmap.yaml from example..."
        cp "$example_file" "$config_file"
    fi

    if [[ ! -f "$config_file" ]]; then
        warn "No netmap.yaml found. Creating minimal configuration..."
        mkdir -p "$PROJECT_ROOT/config"
        cat > "$config_file" << 'EOF'
# MikroTik-NetMap Configuration
# Environment variables are sourced from Infisical via .env file

server:
  host: 0.0.0.0
  port: ${NETMAP_PORT:-8585}
  cors_origins: ["*"]

ping:
  interval: 5
  timeout: 2

api_defaults:
  username: prometheus
  password: "${ROUTER_PASS}"
  api_type: classic
  port: 8728

devices: []
maps: []
links: []

traffic:
  enabled: true
  interval: 30

discovery:
  enabled: true
  interval: 300
  protocols: [mndp, lldp]
  auto_add_devices: false
  auto_add_links: false
EOF
        success "Created minimal netmap.yaml configuration"
    fi

    success "Configuration update completed"
}

# Create enhanced Docker Compose with Infisical
create_docker_infisical_example() {
    log "Creating Docker Compose with Infisical secrets example..."

    cat > "$PROJECT_ROOT/docker-compose.infisical.yml" << 'EOF'
# MikroTik-NetMap — Enhanced Docker Compose with Infisical Secrets
#
# This example shows production-ready deployment with Infisical
# secrets management and enhanced security.

services:
  netmap:
    build: .
    container_name: mikrotik-netmap-infisical
    restart: unless-stopped
    ports:
      - "${NETMAP_PORT:-8585}:8585"
    volumes:
      - ./config:/app/config:ro
      - netmap_data:/app/data
    # Environment from Infisical-generated .env
    env_file:
      - .env
    environment:
      - NETMAP_CONFIG=/app/config/netmap.yaml
      # Production overrides
      - PYTHONUNBUFFERED=1
      - FLASK_ENV=production
    # Resource limits for production
    deploy:
      resources:
        limits:
          cpus: "2.0"
          memory: 1G
        reservations:
          cpus: "0.5"
          memory: 256M
    # Health check
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8585/api/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 30s
    # Security
    read_only: false
    tmpfs:
      - /tmp
    security_opt:
      - no-new-privileges:true

volumes:
  netmap_data:

# Usage:
# 1. Generate .env from Infisical:
#    ./scripts/infisical-sync.sh --generate-env
#
# 2. Start with Infisical integration:
#    docker-compose -f docker-compose.infisical.yml up -d
#
# 3. Access NetMap:
#    http://localhost:8585
#
# 4. Monitor logs:
#    docker-compose -f docker-compose.infisical.yml logs -f netmap
EOF

    success "Created docker-compose.infisical.yml with enhanced configuration"
}

# Main execution
main() {
    case "${1:-}" in
        --setup)
            check_prerequisites
            setup_authentication
            ;;
        --migrate)
            migrate_from_env
            ;;
        --verify)
            verify_integration
            ;;
        --test)
            test_device_connections
            ;;
        --docker)
            test_docker_integration
            ;;
        --generate-env)
            generate_env_file
            ;;
        --update-config)
            update_netmap_config
            ;;
        --create-docker-example)
            create_docker_infisical_example
            ;;
        --full-integration)
            check_prerequisites
            setup_authentication
            migrate_from_env
            generate_env_file
            update_netmap_config
            verify_integration
            test_docker_integration
            create_docker_infisical_example
            ;;
        --help|*)
            echo "MikroTik-NetMap — Infisical Integration"
            echo
            echo "Usage: $0 [OPTION]"
            echo
            echo "Setup:"
            echo "  --setup              Initial Infisical authentication"
            echo "  --migrate            Migrate secrets from .env to Infisical"
            echo "  --full-integration   Complete setup process"
            echo
            echo "Testing:"
            echo "  --verify             Verify Infisical integration"
            echo "  --docker             Test Docker integration"
            echo "  --test               Test device connections"
            echo "  --generate-env       Generate .env from Infisical"
            echo
            echo "Configuration:"
            echo "  --update-config      Update netmap.yaml configuration"
            echo "  --create-docker-example  Create enhanced Docker Compose"
            echo
            echo "Examples:"
            echo "  $0 --setup          # First time setup"
            echo "  $0 --migrate        # Migrate from .env file"
            echo "  $0 --docker         # Test Docker integration"
            echo "  $0 --test           # Test network connections"
            echo
            echo "Environment variables:"
            echo "  ENVIRONMENT          Target environment (default: production)"
            ;;
    esac
}

main "$@"