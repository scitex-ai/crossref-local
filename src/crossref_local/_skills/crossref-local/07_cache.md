---
description: |
  [TOPIC] Cache
  [DETAILS] Disk-based caching of paper metadata for efficient re-querying and reduced
tags: [crossref-local-cache, crossref-local]
package: crossref-local
skill: cache
---


# Paper Cache

Disk-based caching of paper metadata for efficient re-querying and reduced
context usage. Stored under `$SCITEX_DIR/crossref-local/runtime/cache/` (defaulting to `~/.scitex/crossref-local/runtime/cache/`) as JSON files.

## Public API (`crossref_local.cache`)

```python
from crossref_local import cache

cache.create(name, query=None, dois=None, papers=None,
             limit=1000, offset=0) -> CacheInfo
cache.append(name, query=None, dois=None, limit=1000, offset=0) -> CacheInfo
cache.load(name) -> list[dict]
cache.query(name, fields=None, include_abstract=False,
            include_references=False, include_citations=False,
            year_min=None, year_max=None, journal=None,
            limit=None) -> list[dict]
cache.query_dois(name) -> list[str]
cache.stats(name) -> dict
cache.info(name) -> CacheInfo
cache.exists(name) -> bool
cache.list_caches() -> list[CacheInfo]
cache.delete(name) -> bool
cache.export(name, output_path, format="json", fields=None) -> str
```

## `CacheInfo` Dataclass

```python
@dataclass
class CacheInfo:
    name: str
    path: str
    size_bytes: int
    paper_count: int
    created_at: str
    query: Optional[str] = None

    def to_dict(self) -> dict  # includes size_mb
```

## Workflows

### Build a Topic Cache

```python
from crossref_local import cache

# From search query
info = cache.create("epilepsy", query="epilepsy seizure prediction", limit=500)
print(f"Cached {info.paper_count} papers ({info.size_bytes / 1e6:.1f} MB)")

# From explicit DOIs
info = cache.create("my_papers", dois=["10.1038/nature12373", ...])

# From pre-fetched dicts (skips DB calls)
papers = [{"doi": "...", "title": "..."}]
info = cache.create("imported", papers=papers)
```

### Query with Field Projection

```python
# Minimal fields — efficient for context
papers = cache.query("epilepsy", fields=["doi", "title", "year"])

# Default fields: doi, title, authors, year, journal
papers = cache.query("epilepsy")

# Add optional fields
papers = cache.query("epilepsy",
                     include_abstract=True,
                     include_citations=True,
                     include_references=True)

# With filters
papers = cache.query("epilepsy",
                     year_min=2018, year_max=2024,
                     journal="Nature",
                     limit=50)
```

### Statistics

```python
stats = cache.stats("epilepsy")
# Returns:
# {
#   "paper_count": 487,
#   "year_range": {"min": 1995, "max": 2024},
#   "year_distribution": {2020: 45, 2021: 62, ...},
#   "with_abstract": 312,
#   "abstract_coverage": 64.1,
#   "top_journals": [{"journal": "Brain", "count": 23}, ...],
#   "citation_stats": {"total": 45321, "mean": 93.1, "max": 8432}
# }
```

### Cache Management

```python
# List all caches
for ci in cache.list_caches():
    print(f"{ci.name}: {ci.paper_count} papers")

# Check if exists
if cache.exists("epilepsy"):
    ...

# Append new papers
cache.append("epilepsy", query="seizure threshold", limit=200)

# Get just DOIs
dois = cache.query_dois("epilepsy")

# Export
cache.export("epilepsy", "papers.bib", format="bibtex")
cache.export("epilepsy", "papers.csv", format="csv")
cache.export("epilepsy", "dois.txt", format="dois")
cache.export("epilepsy", "papers.json", format="json")

# Delete
cache.delete("epilepsy")
```

## Export Formats

| Format | Description |
|--------|-------------|
| `json` | List of paper dicts |
| `csv` | Tabular format |
| `bibtex` | BibTeX entries |
| `dois` | One DOI per line |

## Cache Directory

Default: `$SCITEX_DIR/crossref-local/runtime/cache/` (where `$SCITEX_DIR`
defaults to `~/.scitex`). Override via `CROSSREF_LOCAL_CACHE_DIR` env var.

- `{name}.json` — paper data
- `{name}.meta.json` — creation metadata (query, timestamps, counts)
