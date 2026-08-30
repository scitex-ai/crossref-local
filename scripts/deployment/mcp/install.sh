#!/bin/bash
# -*- mode: sh -*-
# Install CrossRef Local MCP server as systemd service
#
# Usage:
#   ./scripts/deployment/mcp/install.sh [--user USER] [--port PORT]
#
# Environment:
#   SUDO_PASSWORD - For non-interactive sudo (optional)
#
# The corpus lives in the fleet's shared store, so there is no data path to
# point the service at any more. The server resolves its own store through
# scitex_dev.store.host_store(), which reaches this host's store by default.
#
# To override that, put SCITEX_STORE_DSN in /etc/crossref-mcp.env (the unit
# below reads it if present). This installer deliberately never reads, prints
# or writes a DSN: a unit file under /etc/systemd/system is world-readable and
# a DSN can carry a password.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"

# Defaults
SERVICE_NAME="crossref-mcp"
SERVICE_USER="${USER:-$(whoami)}"
SERVICE_PORT="8082"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

error() { echo -e "${RED}ERROR:${NC} $1" >&2; }
warn()  { echo -e "${YELLOW}WARNING:${NC} $1"; }
info()  { echo -e "${GREEN}✓${NC} $1"; }

usage() {
    cat <<EOF
Install CrossRef Local MCP server as systemd service

Usage: $0 [OPTIONS]

Options:
  --user USER    Service user (default: $SERVICE_USER)
  --port PORT    MCP server port (default: 8082)
  --uninstall    Remove the service
  -h, --help     Show this help

Example:
  $0 --port 8082
  $0 --uninstall

Store override (optional): put SCITEX_STORE_DSN in /etc/crossref-mcp.env.

After installation:
  make mcp-status   # Check service status
  make mcp-logs     # View logs
EOF
}

# Parse arguments
UNINSTALL=false
while [[ $# -gt 0 ]]; do
    case "$1" in
        --user) SERVICE_USER="$2"; shift 2 ;;
        --port) SERVICE_PORT="$2"; shift 2 ;;
        --uninstall) UNINSTALL=true; shift ;;
        -h|--help) usage; exit 0 ;;
        *) error "Unknown option: $1"; usage; exit 1 ;;
    esac
done

# Get crossref-local binary path
CROSSREF_BIN=$(which crossref-local 2>/dev/null || echo "/usr/local/bin/crossref-local")
if [[ ! -x "$CROSSREF_BIN" ]]; then
    # Try venv
    if [[ -x "$PROJECT_ROOT/.venv/bin/crossref-local" ]]; then
        CROSSREF_BIN="$PROJECT_ROOT/.venv/bin/crossref-local"
    else
        error "crossref-local not found. Run: make install"
        exit 1
    fi
fi

# Uninstall
if $UNINSTALL; then
    echo "Removing $SERVICE_NAME service..."
    sudo systemctl stop "$SERVICE_NAME" 2>/dev/null || true
    sudo systemctl disable "$SERVICE_NAME" 2>/dev/null || true
    sudo rm -f "/etc/systemd/system/$SERVICE_NAME.service"
    sudo systemctl daemon-reload
    info "Service removed"
    exit 0
fi

# There is nothing to validate here any more. The installer used to refuse
# unless a corpus FILE existed at $DB_PATH; the corpus is now a store the
# server opens at request time, and pre-flighting it would mean opening a
# connection this script has no business holding.

echo "Installing CrossRef MCP Server"
echo "=============================="
echo ""
echo "  Service:  $SERVICE_NAME"
echo "  User:     $SERVICE_USER"
echo "  Port:     $SERVICE_PORT"
echo "  Binary:   $CROSSREF_BIN"
echo ""

# Generate service file
SERVICE_FILE=$(mktemp)
cat > "$SERVICE_FILE" <<EOF
# CrossRef Local MCP Server
# Installed by: scripts/mcp/install.sh
# Date: $(date -Iseconds)

[Unit]
Description=CrossRef Local MCP Server
Documentation=https://github.com/ywatanabe1989/crossref-local
After=network.target

[Service]
Type=simple
User=$SERVICE_USER
Group=$SERVICE_USER

# Optional store override. Absent, the server reaches this host's own store
# via scitex_dev.store.host_store(). Kept in a separate file (mode 0600,
# operator-owned) rather than inline, so no connection string is written into
# a world-readable unit. The leading '-' makes the file optional.
EnvironmentFile=-/etc/crossref-mcp.env
ExecStart=$CROSSREF_BIN run-server-mcp -t http --host 0.0.0.0 --port $SERVICE_PORT

Restart=always
RestartSec=5

# Security
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF

# Install
echo "Installing service..."
sudo cp "$SERVICE_FILE" "/etc/systemd/system/$SERVICE_NAME.service"
rm "$SERVICE_FILE"

sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE_NAME"
sudo systemctl restart "$SERVICE_NAME"

# Wait and check
sleep 2
if systemctl is-active --quiet "$SERVICE_NAME"; then
    info "Service installed and running!"
    echo ""
    echo "  Status:  sudo systemctl status $SERVICE_NAME"
    echo "  Logs:    journalctl -u $SERVICE_NAME -f"
    echo "  Test:    curl http://localhost:$SERVICE_PORT/mcp"
    echo ""
    echo "MCP client configuration:"
    echo '  {'
    echo '    "mcpServers": {'
    echo '      "crossref-remote": {'
    echo "        \"url\": \"http://$(hostname):$SERVICE_PORT/mcp\""
    echo '      }'
    echo '    }'
    echo '  }'
else
    error "Service failed to start"
    echo ""
    echo "Check logs: journalctl -u $SERVICE_NAME -n 50"
    exit 1
fi
