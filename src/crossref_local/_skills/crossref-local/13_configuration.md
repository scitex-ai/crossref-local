---
description: |
  [TOPIC] Configuration
  [DETAILS] crossref-local supports two access modes: direct SQLite (`db`) and HTTP API
tags: [crossref-local-configuration, crossref-local]
package: crossref-local
skill: configuration
---


# Configuration

crossref-local supports two access modes: direct SQLite (`db`) and HTTP API
(`http`). Mode is auto-detected from environment variables.

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `CROSSREF_LOCAL_DB` | Path to SQLite database file | auto-detect |
| `SCITEX_SCHOLAR_CROSSREF_DB` | Alternative DB path (higher priority) | — |
| `CROSSREF_LOCAL_API_URL` | HTTP API URL | `http://localhost:31291` |
| `CROSSREF_LOCAL_MODE` | Force mode: `db`, `http`, or `auto` | `auto` |
| `CROSSREF_LOCAL_HOST` | Relay server bind host | `0.0.0.0` |
| `CROSSREF_LOCAL_PORT` | Relay server port | `31291` |
| `CROSSREF_LOCAL_MCP_HOST` | MCP HTTP server host | `localhost` |
| `CROSSREF_LOCAL_MCP_PORT` | MCP HTTP server port | `8082` |

## Auto-Detection Order

1. `SCITEX_SCHOLAR_CROSSREF_DB` env var
2. `CROSSREF_LOCAL_DB` env var
3. `./data/crossref.db` (cwd)
4. `$SCITEX_DIR/crossref-local/runtime/crossref.db` (runtime state dir)
5. `~/.crossref_local/crossref.db` (legacy, deprecated)

## Python API

```python
import crossref_local as crl

# DB mode — direct SQLite access
crl.configure("/path/to/crossref.db")

# HTTP mode — connect to relay server
crl.configure_http("http://localhost:31291")
crl.configure_http()  # uses default http://localhost:31291

# configure_remote is a backward-compat alias for configure_http
crl.configure_remote("http://myserver:31291")

# Query current mode
mode = crl.get_mode()   # returns "db" or "http"

# Get database statistics
info = crl.info()
# Returns: {"mode": "db", "status": "ok", "db_path": "...",
#           "works": 167_000_000, "fts_indexed": ..., "citations": ...}
```

## Signatures

```python
configure(db_path: str) -> None
configure_http(api_url: str = "http://localhost:31291") -> None
configure_remote(api_url: str = "http://localhost:31291") -> None  # alias
get_mode() -> str   # "db" or "http"
info() -> dict
```

## SSH Tunnel (Remote DB)

```bash
# On local machine: tunnel port 31291 from remote server
ssh -L 31291:127.0.0.1:31291 your-server

# In Python
crl.configure_http()   # default localhost:31291 — now tunneled to server
```

## HTTP Relay Server

Start a relay server to expose the local SQLite DB over HTTP:

```bash
crossref-local relay                    # binds 0.0.0.0:31291
crossref-local relay --port 8080        # custom port
crossref-local relay --force            # kill existing process on port
```

`run_server` is implemented in `crossref_local._server`.
