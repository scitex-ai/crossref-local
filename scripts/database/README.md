# Database Scripts — retired

This directory used to hold the corpus build pipeline: a bulk loader, index
creation, a citations-table rebuild, journal tables, a full-text index build,
an abstract-ratio count, connection diagnostics and a schema dump. Every one
of them produced or maintained a single on-disk artifact, `data/crossref.db`.

**That artifact no longer exists.** The corpus lives in the fleet's shared
store primitive (`scitex_dev.store`), reached through
`crossref_local._core.store`. Nothing in this package opens a database file,
so the pipeline had no output anything could consume and the scripts were
removed rather than left to rot.

The one live script, `10_differential_update.py`, was ported into the package
and is now `crossref_local._core.ingest`.

## What replaced it

| Old step | Now |
| --- | --- |
| Bulk load + differential update | `crossref-local update-db` (`crossref_local._core.ingest`) |
| Index creation / maintenance | Nothing to run — indexing is declared per field in `crossref_local._core.store` and enforced by the primitive |
| Full-text index build | Nothing to run — `title` / `abstract` / `authors` are fields on the work, written in the same upsert |
| Row counts / abstract ratio | `crossref-local sync-stats`, read back by `crossref-local status` |
| Schema dump / connection check | `crossref-local status` |

## Usage

```bash
crossref-local update-db                 # incremental ingest from the CrossRef REST API
crossref-local update-db --dry-run       # count what would be upserted, write nothing
crossref-local sync-stats                # recompute the exact-count cache
crossref-local status                    # store resolution + cached counts
```

The ingest engine is an ordinary importable module, so it can also be driven
directly:

```bash
python -m crossref_local._core.ingest --since 2026-03-01
```

<!-- EOF -->
