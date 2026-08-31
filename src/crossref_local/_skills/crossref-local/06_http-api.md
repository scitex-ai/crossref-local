---
description: |
  [TOPIC] HTTP API — crossref-local FastAPI server
  [DETAILS] Standalone FastAPI app in `_server/` exposing search/get/citation/collection endpoints over this host's shared store. Boot with `crossref-local relay` or `uvicorn crossref_local._server:app`.
tags: [crossref-local-http-api]
---

# HTTP API — crossref-local

The `crossref_local._server` package exposes this host's CrossRef corpus as
a FastAPI service. Routers live alongside `__init__.py`:

- `routes_works.py` — work search + retrieval
- `routes_citations.py` — citation graph queries
- `routes_collections.py` — saved query collections
- `routes_compat.py` — legacy `/search/`, `/stats/` shim

## Endpoints

### Root / health

| Method | Path | Handler | Returns |
|--------|------|---------|---------|
| GET | `/` | root | API name, version, endpoint map |
| GET | `/health` | health | Store reachability + a credential-free `store` name |
| GET | `/info` | info | Cached corpus counts + `counts_source` |

### Works

| Method | Path | Returns |
|--------|------|---------|
| GET | `/works?q=<query>` | `SearchResponse` — full-text search across the corpus (scan; see [14_search.md](14_search.md)) |
| GET | `/works/{doi:path}` | `WorkResponse` (or null) — fetch by DOI |
| POST | `/works/batch` | `BatchResponse` — bulk DOI lookup |

### Citations

| Method | Path | Returns |
|--------|------|---------|
| GET | `/citations/{doi:path}/citing` | `CitingResponse` — works that cite this DOI |
| GET | `/citations/{doi:path}/cited` | `CitedResponse` — works cited by this DOI |
| GET | `/citations/{doi:path}/count` | `CitationCountResponse` — counts only |
| GET | `/citations/{doi:path}/network` | `CitationNetworkResponse` — local graph |

### Collections

| Method | Path | Returns |
|--------|------|---------|
| GET | `/collections` | List collections |
| POST | `/collections` | Create a collection (`CollectionInfo`) |
| GET | `/collections/{name}` | Collection contents |
| GET | `/collections/{name}/stats` | Per-collection stats |
| GET | `/collections/{name}/download` | Bulk export |
| DELETE | `/collections/{name}` | Drop a collection |

### Legacy compat

| Method | Path | Notes |
|--------|------|-------|
| GET | `/search/` | Pre-`/works` search shape — kept for old clients |
| GET | `/stats/` | Pre-`/info` stats shape |

## Boot

```bash
crossref-local relay --host 0.0.0.0 --port 31291
# or
uvicorn crossref_local._server:app --port 31291
```

See `13_configuration.md` for env vars (store, mode, relay).
