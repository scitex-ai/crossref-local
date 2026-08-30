---
description: |
  [TOPIC] Installation
  [DETAILS] pip install crossref-local. Pure-Python wheels; the corpus lives in this host's shared store, populated by `update-db`. Optional [api], [viz], [mcp] extras.
tags: [crossref-local-installation]
---

# Installation

## Requirements

- Python 3.10+
- `scitex-dev>=0.57.0`
- Access to this host's shared store

## Standard

```bash
pip install crossref-local
```

Pulls `click>=8.0`, `rich>=13.0`, and `scitex-dev>=0.57.0`.

There is **no database file to download and no build step**. The corpus
lives in the fleet's shared store — one PostgreSQL-backed store per host,
resolved by `scitex_dev.store.host_store()`. Populate and refresh it
incrementally from the CrossRef REST API:

```bash
crossref-local update-db --yes     # initial fill and ongoing refresh
crossref-local sync-stats          # refresh the exact-count cache
```

Set `SCITEX_STORE_DSN` only to point at a store other than this host's own
— see [12_env-vars.md](12_env-vars.md).

## Optional extras

| Extra | Purpose |
|---|---|
| `api` | FastAPI HTTP relay server (`crossref-local relay`) |
| `viz` | Matplotlib + networkx for citation-network plots |
| `mcp` | MCP server (`crossref-local mcp start`) |
| `dev` | Test + lint tooling |
| `docs` | Sphinx + RTD theme |
| `all` | Everything above |

```bash
pip install 'crossref-local[api,viz,mcp]'
```

## Verify

```bash
python -c "import crossref_local; print(crossref_local.__version__)"
crossref-local --version
crossref-local show-status        # also shows access mode + store
```

## Editable install (development)

```bash
git clone https://github.com/ywatanabe1989/crossref-local
cd crossref-local
pip install -e '.[dev]'
```

## DB vs HTTP mode

Two operating modes share the same Python + CLI surface:

- **DB mode** (default, if a store target resolves) — direct reads against
  this host's shared store
- **HTTP mode** (`--http`) — talks to a `crossref-local relay` server, for a
  machine with no store of its own

See [13_configuration.md](13_configuration.md) for env vars and mode
selection.
