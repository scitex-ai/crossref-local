#!/bin/bash
# -*- coding: utf-8 -*-
# File: scripts/deployment/run_docker.sh
# Description: Run crossref-local in Docker container

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"
IMAGE_NAME="crossref-local"
CONTAINER_NAME="crossref-local"
PORT="${CROSSREF_LOCAL_PORT:-3333}"

# The corpus is a store the package connects to, not a directory to bind in,
# so there is no data volume. SCITEX_STORE_DSN is forwarded from this shell
# when set, and never echoed: a DSN can carry a password.
STORE_ENV=()
if [[ -n "${SCITEX_STORE_DSN:-}" ]]; then
    STORE_ENV=(-e "SCITEX_STORE_DSN=${SCITEX_STORE_DSN}")
fi

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

usage() {
    cat << EOF
Usage: $(basename "$0") [OPTIONS] [COMMAND]

Run crossref-local in a Docker container.

COMMANDS:
    api         Start API server (default)
    serve       Start MCP server
    search      Run search command
    shell       Open interactive shell

OPTIONS:
    -p, --port PORT    Port for API server (default: 3333)
    -b, --build        Force rebuild of Docker image
    -h, --help         Show this help message

EXAMPLES:
    $(basename "$0")                        # Start API server
    $(basename "$0") --port 8080 api        # API on custom port
    $(basename "$0") search "CRISPR"        # Run search
    $(basename "$0") shell                  # Interactive shell

ENVIRONMENT:
    CROSSREF_LOCAL_PORT   API port (default: 3333)
    SCITEX_STORE_DSN      Optional store override, forwarded into the container
EOF
}

build_image() {
    echo -e "${GREEN}Building Docker image...${NC}"
    docker build -t "${IMAGE_NAME}" "${PROJECT_ROOT}"
}

check_image() {
    if [[ "$(docker images -q ${IMAGE_NAME} 2>/dev/null)" == "" ]] || [[ "${BUILD:-0}" == "1" ]]; then
        build_image
    fi
}

run_api() {
    echo -e "${GREEN}Starting API server on port ${PORT}...${NC}"
    docker run --rm -it \
        --name "${CONTAINER_NAME}" \
        -p "${PORT}:3333" \
        ${STORE_ENV[@]+"${STORE_ENV[@]}"} \
        "${IMAGE_NAME}" \
        crossref-local api --host 0.0.0.0 --port 3333
}

run_serve() {
    echo -e "${GREEN}Starting MCP server...${NC}"
    docker run --rm -it \
        --name "${CONTAINER_NAME}" \
        ${STORE_ENV[@]+"${STORE_ENV[@]}"} \
        "${IMAGE_NAME}" \
        crossref-local serve
}

run_command() {
    docker run --rm -it \
        ${STORE_ENV[@]+"${STORE_ENV[@]}"} \
        "${IMAGE_NAME}" \
        crossref-local "$@"
}

run_shell() {
    docker run --rm -it \
        ${STORE_ENV[@]+"${STORE_ENV[@]}"} \
        "${IMAGE_NAME}" \
        /bin/bash
}

# Parse arguments
BUILD=0
COMMAND="api"

while [[ $# -gt 0 ]]; do
    case "$1" in
        -p|--port) PORT="$2"; shift 2 ;;
        -b|--build) BUILD=1; shift ;;
        -h|--help) usage; exit 0 ;;
        api|serve|shell) COMMAND="$1"; shift ;;
        search|get|count|info|impact-factor)
            COMMAND="cmd"
            CMD_ARGS=("$@")
            break
            ;;
        *) echo -e "${RED}Unknown option: $1${NC}"; usage; exit 1 ;;
    esac
done

check_image

case "$COMMAND" in
    api) run_api ;;
    serve) run_serve ;;
    shell) run_shell ;;
    cmd) run_command "${CMD_ARGS[@]}" ;;
esac
