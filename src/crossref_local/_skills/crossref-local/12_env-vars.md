---
description: |
  [TOPIC] Env Vars
  [DETAILS] see general/10_arch-environment-variables.md.
tags: [crossref-local-env-vars, crossref-local]
---


# crossref-local — Environment Variables

The corpus lives in the fleet's shared store, so there is no database path
to set. Store resolution belongs to `scitex_dev.store.host_store()`;
crossref-local never builds a connection string and never reads one
directly.

Some vars carry the upstream `SCITEX_SCHOLAR_CROSSREF_*` prefix because
crossref-local ships the CrossRef backend for scitex-scholar (they were
coined there and kept stable for back-compat). Where both spellings exist,
the `SCITEX_SCHOLAR_*` one wins.

## Store

| Variable | Purpose | Default | Type |
|---|---|---|---|
| `SCITEX_STORE_DSN` | Connection string for the shared store. Read by `scitex_dev.store.host_store()`, not by this package. | unset — `host_store()` then resolves this host's own PostgreSQL over its UNIX socket | string |

## Mode selection

| Variable | Purpose | Default | Type |
|---|---|---|---|
| `SCITEX_SCHOLAR_CROSSREF_MODE` | Backend mode: `db` (read the shared store directly), `http` (talk to a relay), or `auto`. `local`/`store` and `remote`/`api` are accepted aliases. | `auto` | string |
| `CROSSREF_LOCAL_MODE` | Same, lower priority than the `SCITEX_SCHOLAR_*` spelling. | `auto` | string |
| `CROSSREF_LOCAL_API_URL` | Relay URL for `http` mode. Setting it also selects `http` under `auto`. | `http://localhost:31291` | url |

## Relay server (`crossref-local relay`)

| Variable | Purpose | Default | Type |
|---|---|---|---|
| `SCITEX_SCHOLAR_CROSSREF_HOST` | Bind host. | `0.0.0.0` | string |
| `CROSSREF_LOCAL_HOST` | Same, lower priority. | `0.0.0.0` | string |
| `SCITEX_SCHOLAR_CROSSREF_PORT` | Bind port. | `31291` | int |
| `CROSSREF_LOCAL_PORT` | Same, lower priority. | `31291` | int |

## MCP server (`crossref-local mcp start`)

| Variable | Purpose | Default | Type |
|---|---|---|---|
| `CROSSREF_LOCAL_MCP_HOST` | Host for HTTP/SSE transport. | `localhost` | string |
| `CROSSREF_LOCAL_MCP_PORT` | Port for HTTP/SSE transport. | `8082` | int |

## Other

| Variable | Purpose | Default | Type |
|---|---|---|---|
| `CROSSREF_LOCAL_CACHE_DIR` | Override the topic-cache directory. | `$SCITEX_DIR/crossref-local/runtime/cache/` | path |
| `CROSSREF_LOCAL_UPDATE_FEED` | Point `update-db` at a local JSON feed file instead of the CrossRef REST API — for CI, cron dry-runs and air-gapped hosts. | unset (network) | path |
| `SCITEX_DIR` | Root of the SciTeX state tree. | `~/.scitex` | path |

## Feature flags

None. All vars are configuration values.

## Removed

| Variable | Note |
|---|---|
| `CROSSREF_LOCAL_DB` | Named a database file. There is no file: the corpus is in the shared store. |
| `SCITEX_SCHOLAR_CROSSREF_DB` | Same. |

## Notes

- Under `MODE=auto`, crossref-local checks the mode vars, then
  `CROSSREF_LOCAL_API_URL`, and finally falls back to `db` if a store target
  resolves — `http` if it does not. Resolution only: no connection is opened
  to answer that question.
- These vars are shared with scitex-scholar; set them once in the user
  environment and both packages will honor them.

## Audit

```bash
grep -rhoE 'SCITEX_[A-Z0-9_]+|CROSSREF_LOCAL_[A-Z0-9_]+' \
  $HOME/proj/crossref-local/src/ | sort -u
```
