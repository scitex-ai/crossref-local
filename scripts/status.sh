#!/bin/bash
# -*- mode: sh -*-
# ============================================================================
# CrossRef Local - Overall status check
# ============================================================================
# Usage: status.sh [OPTIONS]
#
# Options:
#   -h, --help    Show this help message and exit
#   -q, --quiet   Minimal output (exit code only)
#   -j, --json    Output status as JSON
#
# Reports whether the corpus store resolves, and what the MCP server is doing.
#
# The store is not probed here. `crossref-local status` already resolves it
# through scitex_dev.store.host_store(), so this script asks the package and
# reports the answer instead of reimplementing a connection check in shell —
# a second implementation would be the one that drifts. No connection string
# is read or printed anywhere below: a DSN can carry a password, and the
# package deliberately reports a describe() name in its place.
#
# Examples:
#   ./status.sh           # Full status report
#   ./status.sh --quiet   # Exit 0 if healthy, 1 if issues
#   ./status.sh --json    # JSON output for scripting
# ============================================================================

set -euo pipefail

# -----------------------------------------------------------------------------
# Argument parsing
# -----------------------------------------------------------------------------
show_help() {
    # Print the banner-delimited header block above. The previous sed range
    # stopped at the SECOND banner line, so --help printed only the title and
    # never the options it was documenting.
    awk '/^# ={5,}/ { n++; next }
         n >= 3      { exit }
         n >= 1      { sub(/^# ?/, ""); print }' "$0"
    exit 0
}

QUIET=false
JSON=false

while [[ $# -gt 0 ]]; do
    case $1 in
    -h | --help)
        show_help
        ;;
    -q | --quiet)
        QUIET=true
        shift
        ;;
    -j | --json)
        JSON=true
        shift
        ;;
    *)
        echo "Unknown option: $1" >&2
        echo "Use --help for usage information" >&2
        exit 1
        ;;
    esac
done

# -----------------------------------------------------------------------------
# Setup
# -----------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Prefer the project venv, so `make status` reports on the same install
# `make test` runs against rather than on whatever is first on PATH.
CLI=""
if [ -x "$PROJECT_ROOT/.venv/bin/crossref-local" ]; then
    CLI="$PROJECT_ROOT/.venv/bin/crossref-local"
elif command -v crossref-local > /dev/null 2>&1; then
    CLI="$(command -v crossref-local)"
fi

STORE_JSON=""

# -----------------------------------------------------------------------------
# Helper functions
# -----------------------------------------------------------------------------
probe_store() {
    # Ask the package whether its store resolves. `status --json` exits
    # non-zero and reports {"status": "error"} when it cannot reach the
    # store, so the exit code is the whole answer.
    [ -n "$CLI" ] || return 1
    STORE_JSON="$("$CLI" status --json 2> /dev/null)" || return 1
    [ -n "$STORE_JSON" ] || return 1
    case "$STORE_JSON" in
    *'"status": "error"'*) return 1 ;;
    esac
    return 0
}

json_field() {
    # Pull one scalar out of the payload above. The shape is fixed
    # (json.dumps(indent=2) over a flat dict), not arbitrary JSON.
    printf '%s\n' "$STORE_JSON" \
        | grep -m1 "\"$1\"" \
        | sed -e 's/^[^:]*:[[:space:]]*//' -e 's/,$//' -e 's/^"//' -e 's/"$//' \
        || true
}

# -----------------------------------------------------------------------------
# JSON output
# -----------------------------------------------------------------------------
if $JSON; then
    if probe_store; then
        RESOLVES=true
    else
        RESOLVES=false
    fi

    cat << EOF
{
  "healthy": $RESOLVES,
  "store": {
    "resolves": $RESOLVES,
    "cli": "${CLI:-}"
  },
  "info": ${STORE_JSON:-null}
}
EOF
    if [ "$RESOLVES" = true ]; then exit 0; else exit 1; fi
fi

# -----------------------------------------------------------------------------
# Quiet mode
# -----------------------------------------------------------------------------
if $QUIET; then
    if probe_store; then exit 0; else exit 1; fi
fi

# -----------------------------------------------------------------------------
# Full status report
# -----------------------------------------------------------------------------
HEALTH_OK=true

echo "╔════════════════════════════════════════════════════════════╗"
echo "║           CROSSREF LOCAL - STATUS                         ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""

# Corpus store
echo "=== Corpus Store ==="
if [ -z "$CLI" ]; then
    HEALTH_OK=false
    echo "  ✗ crossref-local not found"
    echo "    Hint: run 'make install' (or activate the venv)"
elif probe_store; then
    echo "  ✓ crossref-local: $CLI"
    echo "  ✓ Store: $(json_field store)"
else
    HEALTH_OK=false
    echo "  ✗ Store does NOT resolve"
    echo "    Hint: check SCITEX_STORE_DSN, or that this host's store is up"
    echo "    Detail: $CLI status"
fi
echo ""

# Quick Stats
echo "=== Quick Stats ==="
if [ -n "$STORE_JSON" ]; then
    echo "  Works:      $(json_field works)"
    echo "  Searchable: $(json_field fts_indexed)"
    echo "  Citations:  $(json_field citations)"
    echo "  Source:     $(json_field counts_source) (as of $(json_field counts_computed_at))"
    echo "    Counts come from the cache collection, never from a scan."
    echo "    Refresh with: crossref-local sync-stats"
else
    echo "  (store not available)"
fi
echo ""

# MCP Server
echo "=== MCP Server ==="
"$SCRIPT_DIR/deployment/mcp/status.sh" 2> /dev/null || echo "  (MCP status script not available)"

# Help
echo "Commands:"
echo "  crossref-local status  - Store details and counts"
echo "  crossref-local update-db - Ingest recent works into the store"
echo "  make mcp-status        - MCP server details"

# Exit with health status
$HEALTH_OK && exit 0 || exit 1
