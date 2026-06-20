---
description: |
  [TOPIC] Installation
  [DETAILS] pip install crossref-local. Pure-Python wheels; SQLite DB downloaded separately. Optional [api], [viz], [mcp] extras.
tags: [crossref-local-installation]
---

# Installation

## Standard

```bash
pip install crossref-local
```

Pulls `click>=8.0`, `rich>=13.0`, and `scitex-dev`. The 167M-row SQLite
database is fetched on first use (or pointed at by env var — see
[12_env-vars.md](12_env-vars.md)).

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
crossref-local show-status        # also shows DB mode + path
```

## Editable install (development)

```bash
git clone https://github.com/ywatanabe1989/crossref-local
cd crossref-local
pip install -e '.[dev]'
```

## DB vs HTTP mode

Two operating modes share the same Python + CLI surface:

- **DB mode** (default, if a local DB is found) — direct SQLite queries
- **HTTP mode** (`--http`) — talks to a `crossref-local relay` server

See [13_configuration.md](13_configuration.md) for env vars and mode
selection.
