---
description: |
  [TOPIC] Configuration
  [DETAILS] crossref-local supports two access modes: direct store reads (`db`) and HTTP API
tags: [crossref-local-configuration, crossref-local]
package: crossref-local
skill: configuration
---


# Configuration

crossref-local supports two access modes: direct reads against this host's
shared store (`db`) and HTTP API (`http`). Mode is auto-detected from
environment variables.

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `SCITEX_STORE_DSN` | Shared-store connection string, resolved by `scitex_dev.store.host_store()` | this host's own store |
| `CROSSREF_LOCAL_API_URL` | HTTP API URL | `http://localhost:31291` |
| `CROSSREF_LOCAL_MODE` | Force mode: `db`, `http`, or `auto` | `auto` |
| `SCITEX_SCHOLAR_CROSSREF_MODE` | Same, higher priority | `auto` |
| `CROSSREF_LOCAL_HOST` | Relay server bind host | `0.0.0.0` |
| `CROSSREF_LOCAL_PORT` | Relay server port | `31291` |
| `CROSSREF_LOCAL_MCP_HOST` | MCP HTTP server host | `localhost` |
| `CROSSREF_LOCAL_MCP_PORT` | MCP HTTP server port | `8082` |

Full table, including the removed database-path variables:
[12_env-vars.md](12_env-vars.md).

## Mode Auto-Detection Order

1. `SCITEX_SCHOLAR_CROSSREF_MODE`, else `CROSSREF_LOCAL_MODE`
2. `CROSSREF_LOCAL_API_URL` set (or `configure_http()` called) → `http`
3. A store target resolves → `db`, otherwise → `http`

Step 3 resolves a target; it does not open a connection. A store that
resolves but refuses the connection surfaces as the store's own error at
first use, which names the address and the reason.

## Python API

```python
import crossref_local as crl

# DB mode — direct reads against this host's shared store.
# Nothing to configure: scitex-dev resolves the store.

# HTTP mode — connect to relay server
crl.configure_http("http://localhost:31291")
crl.configure_http()  # uses default http://localhost:31291

# configure_remote is a backward-compat alias for configure_http
crl.configure_remote("http://myserver:31291")

# Query current mode
mode = crl.get_mode()   # returns "db" or "http"

# Get corpus statistics
info = crl.info()
# Returns: {"mode": "db", "status": "ok", "store": "<credential-free name>",
#           "works": ..., "fts_indexed": ..., "citations": ...,
#           "counts_source": "exact" | "unavailable",
#           "counts_computed_at": "<ISO timestamp or None>"}
```

`info()` carries a `store` key — a credential-free description of the store
this host reads. It is never the DSN: a DSN can hold a password, and this
value is printed to terminals and returned over HTTP to clients.

Counts come from a cache and are never measured on this path. Refresh them
with `crossref-local sync-stats`; until you do, `counts_source` reads
`"unavailable"` rather than reporting a number nobody measured.

## Signatures

```python
configure_http(api_url: str = "http://localhost:31291") -> None
configure_remote(api_url: str = "http://localhost:31291") -> None  # alias
get_mode() -> str   # "db" or "http"
info() -> dict
refresh_stats() -> dict
```

`configure(db_path)` is **removed**. It named a database file, and there is
no file — the corpus lives in the shared store.

## SSH Tunnel (Remote Relay)

```bash
# On local machine: tunnel port 31291 from the relay host
ssh -L 31291:127.0.0.1:31291 your-server

# In Python
crl.configure_http()   # default localhost:31291 — now tunneled to server
```

## HTTP Relay Server

Start a relay server to expose this host's store over HTTP, for machines
that have no store of their own:

```bash
crossref-local relay                    # binds 0.0.0.0:31291
crossref-local relay --port 8080        # custom port
crossref-local relay --force            # kill existing process on port
```

`run_server` is implemented in `crossref_local._server`.
