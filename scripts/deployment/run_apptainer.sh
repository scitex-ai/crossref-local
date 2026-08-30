#!/bin/bash
# -*- coding: utf-8 -*-
# File: scripts/deployment/run_apptainer.sh
# Description: Run crossref-local with Apptainer/Singularity container

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"
IMAGE="${PROJECT_ROOT}/containers/crossref_local.sif"
OUTPUT_DIR="${PROJECT_ROOT}/output"

# There is no data bind: the corpus is a store the package connects to, not a
# directory. Apptainer passes the host environment through by default, so
# SCITEX_STORE_DSN reaches the container without being named (or printed)
# here — a DSN can carry a password.

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

usage() {
    cat << EOF
Usage: $(basename "$0") [OPTIONS] [COMMAND]

Run crossref-local with Apptainer/Singularity container.

COMMANDS:
    api         Start API server (default)
    serve       Start MCP server
    search      Run search command
    shell       Open interactive shell

OPTIONS:
    -i, --image PATH   Container image path (default: containers/crossref_local.sif)
    -o, --output PATH  Output directory (default: output/)
    -h, --help         Show this help message

EXAMPLES:
    $(basename "$0")                        # Start API server
    $(basename "$0") search "CRISPR"        # Run search
    $(basename "$0") shell                  # Interactive shell

PREREQUISITES:
    Build image first: ./scripts/deployment/build_apptainer.sh
EOF
}

detect_runner() {
    if command -v apptainer &>/dev/null; then
        echo "apptainer"
    elif command -v singularity &>/dev/null; then
        echo "singularity"
    else
        echo -e "${RED}ERROR: Neither apptainer nor singularity found${NC}" >&2
        echo "Install with: ./scripts/deployment/install_apptainer.sh" >&2
        exit 1
    fi
}

check_image() {
    if [[ ! -f "$IMAGE" ]]; then
        echo -e "${RED}ERROR: Image not found: ${IMAGE}${NC}" >&2
        echo "Build it first with: ./scripts/deployment/build_apptainer.sh" >&2
        exit 1
    fi
}

run_container() {
    local RUNNER
    RUNNER=$(detect_runner)
    mkdir -p "${OUTPUT_DIR}"

    ${RUNNER} run \
        --bind "${OUTPUT_DIR}:/output" \
        "${IMAGE}" \
        "$@"
}

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        -i|--image) IMAGE="$2"; shift 2 ;;
        -o|--output) OUTPUT_DIR="$2"; shift 2 ;;
        -h|--help) usage; exit 0 ;;
        api|serve|search|get|count|info|shell)
            break
            ;;
        *) echo -e "${RED}Unknown option: $1${NC}"; usage; exit 1 ;;
    esac
done

check_image

if [[ $# -eq 0 ]]; then
    run_container crossref-local api --host 0.0.0.0
elif [[ "$1" == "shell" ]]; then
    RUNNER=$(detect_runner)
    mkdir -p "${OUTPUT_DIR}"
    ${RUNNER} shell \
        --bind "${OUTPUT_DIR}:/output" \
        "${IMAGE}"
else
    run_container crossref-local "$@"
fi
