---
description: |
  [TOPIC] Python API
  [DETAILS] Public callables grouped by area — search, retrieval, enrichment, citations, checker, cache, export, async.
tags: [crossref-local-python-api]
---

# Python API

```python
import crossref_local as crl
```

## Search + count

| Symbol | Purpose |
|---|---|
| `search(query, limit=...)` | Full-text search → `SearchResult` (scans the works collection — see [14_search.md](14_search.md)) |
| `count(query)` | Count matches without building `Work` objects (same scan) |
| `exists(doi)` | Boolean DOI presence check (keyed read) |

## Retrieval + enrichment

| Symbol | Purpose |
|---|---|
| `get(doi)` | Single `Work` by DOI |
| `get_many(dois)` | Batch DOI lookup |
| `enrich(input, out=...)` | Enrich BibTeX (or list) with metadata |
| `enrich_dois(dois)` | Resolve a DOI list to enriched records |

## Models (dataclasses)

| Symbol | Purpose |
|---|---|
| `Work` | Single record — DOI, title, authors, year, abstract, IF, … |
| `SearchResult` | Iterable container with `.works`, `.total`, `.query` |

## Citations

| Symbol | Purpose |
|---|---|
| `get_citing(doi)` | DOIs citing the given work |
| `get_cited(doi)` | DOIs cited by the given work |
| `get_citation_count(doi)` | Total inbound citations |
| `CitationNetwork` | Graph constructor + traversal |

## Checker

| Symbol | Purpose |
|---|---|
| `check_citations(bibtex_or_dois)` | Validate references → `CheckResult` |
| `check_bibtex(path)` | BibTeX-specific entry-point |
| `check_doi_list(path)` | DOI-list entry-point |
| `CheckResult`, `CitationEntry` | Result dataclasses |

## Cache + export

| Symbol | Purpose |
|---|---|
| `cache.*` | Topic-cache create / query / stats / plots |
| `save(records, path, format=...)` | Write JSON / BibTeX / text |
| `SUPPORTED_FORMATS` | Tuple of supported export formats |

## Configuration

| Symbol | Purpose |
|---|---|
| `configure_http(api_url=...)` | Force HTTP mode |
| `configure_remote(...)` | Configure remote relay (alias of `configure_http`) |
| `get_mode()` | `"db"` or `"http"` |
| `info()` | Status snapshot (mode, `store`, cached counts, `counts_source`) |
| `refresh_stats()` | Recompute the exact-count cache (full scan) |

`configure(db_path)` is removed — there is no database file to point at.

## Async

| Symbol | Purpose |
|---|---|
| `aio.search(...)`, `aio.count_many(...)` | asyncio-friendly variants |

## Jobs

| Symbol | Purpose |
|---|---|
| `jobs.*` | Long-running batch jobs (background workers) |

## See also

- [05_citations.md](05_citations.md), [17_checker.md](17_checker.md), [07_cache.md](07_cache.md), [08_export.md](08_export.md), [09_async.md](09_async.md) — per-area deep-dives
- [04_cli-reference.md](04_cli-reference.md) — CLI mirror of this surface
