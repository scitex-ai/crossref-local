#!/bin/bash
# -*- mode: sh -*-
# Docker management for CrossRef MCP server

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"

CONTAINER_NAME="crossref-mcp"
IMAGE_NAME="crossref-mcp"
PORT="${CROSSREF_LOCAL_MCP_PORT:-8082}"

# The corpus is a store the server connects to, not a file to bind-mount, so
# there is no data volume here. SCITEX_STORE_DSN is forwarded from this
# shell if it is set, and never echoed: a DSN can carry a password.
STORE_ENV=()
if [[ -n "${SCITEX_STORE_DSN:-}" ]]; then
    STORE_ENV=(-e "SCITEX_STORE_DSN=${SCITEX_STORE_DSN}")
fi

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

error() { echo -e "${RED}ERROR:${NC} $1" >&2; }
info()  { echo -e "${GREEN}✓${NC} $1"; }

usage() {
    cat <<EOF
Docker management for CrossRef MCP server

Usage: $0 <command> [OPTIONS]

Commands:
  build       Build Docker image
  run         Run container (build if needed)
  start       Start existing container
  stop        Stop container
  restart     Restart container
  status      Show container status
  logs        Show container logs
  rm          Remove container
  clean       Remove container and image

Options:
  --port PORT MCP server port (default: 8082)

Environment:
  SCITEX_STORE_DSN  Optional store override, forwarded into the container.

Examples:
  $0 run
  $0 logs -f
  $0 stop
EOF
}

cmd_build() {
    echo "Building Docker image..."
    docker build -f "$PROJECT_ROOT/scripts/deployment/mcp/Dockerfile.mcp" \
        -t "$IMAGE_NAME" "$PROJECT_ROOT"
    info "Image built: $IMAGE_NAME"
}

cmd_run() {
    # Nothing to validate: there is no corpus file to find. The server opens
    # the store at request time and reports its own failure honestly.

    # Build if image doesn't exist
    if ! docker image inspect "$IMAGE_NAME" &>/dev/null; then
        cmd_build
    fi

    # Remove existing container if any
    docker rm -f "$CONTAINER_NAME" 2>/dev/null || true

    echo "Starting container..."
    docker run -d \
        --name "$CONTAINER_NAME" \
        -p "$PORT:8082" \
        ${STORE_ENV[@]+"${STORE_ENV[@]}"} \
        --restart unless-stopped \
        "$IMAGE_NAME"

    sleep 2
    if docker ps | grep -q "$CONTAINER_NAME"; then
        info "Container running: $CONTAINER_NAME"
        echo ""
        echo "  Port:   http://localhost:$PORT/mcp"
        echo "  Logs:   make mcp-docker-logs"
        echo "  Stop:   make mcp-docker-stop"
    else
        error "Container failed to start"
        docker logs "$CONTAINER_NAME"
        exit 1
    fi
}

cmd_start() {
    docker start "$CONTAINER_NAME"
    info "Container started"
}

cmd_stop() {
    docker stop "$CONTAINER_NAME"
    info "Container stopped"
}

cmd_restart() {
    docker restart "$CONTAINER_NAME"
    info "Container restarted"
}

cmd_status() {
    echo "=== Docker MCP Status ==="
    if docker ps | grep -q "$CONTAINER_NAME"; then
        echo "  ✓ Container: RUNNING"
        echo "  Port: http://localhost:$PORT/mcp"

        # Test endpoint
        if curl -s -o /dev/null "http://localhost:$PORT/mcp" 2>/dev/null; then
            echo "  ✓ Endpoint: responding"
        else
            echo "  ⚠ Endpoint: not responding"
        fi
    elif docker ps -a | grep -q "$CONTAINER_NAME"; then
        echo "  ○ Container: STOPPED"
        echo "  Start with: make mcp-docker-start"
    else
        echo "  ○ Container: NOT CREATED"
        echo "  Run with: make mcp-docker-run"
    fi
    echo ""
}

cmd_logs() {
    shift 2>/dev/null || true
    docker logs "$@" "$CONTAINER_NAME"
}

cmd_rm() {
    docker rm -f "$CONTAINER_NAME" 2>/dev/null || true
    info "Container removed"
}

cmd_clean() {
    docker rm -f "$CONTAINER_NAME" 2>/dev/null || true
    docker rmi -f "$IMAGE_NAME" 2>/dev/null || true
    info "Container and image removed"
}

# Parse arguments
CMD="${1:-}"
shift || true

while [[ $# -gt 0 ]]; do
    case "$1" in
        --port) PORT="$2"; shift 2 ;;
        -h|--help) usage; exit 0 ;;
        *) break ;;
    esac
done

case "$CMD" in
    build)   cmd_build ;;
    run)     cmd_run ;;
    start)   cmd_start ;;
    stop)    cmd_stop ;;
    restart) cmd_restart ;;
    status)  cmd_status ;;
    logs)    cmd_logs "$@" ;;
    rm)      cmd_rm ;;
    clean)   cmd_clean ;;
    -h|--help|"") usage ;;
    *) error "Unknown command: $CMD"; usage; exit 1 ;;
esac
