# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.9.0] - 2026-08-30

The corpus moves off the embedded file-backed database engine and into the
fleet's shared store primitive (`scitex_dev.store`). See
`docs/adr/0001-corpus-moves-to-the-shared-store.md` for the decision, the
collection mapping, and — in full — the performance this costs and why it
is taken deliberately.

### Removed
- The per-package database layer `_core/db.py`, and with it `Database`,
  `get_db()`, `close_db()` and `connection()`. Consumers now hold a
  `scitex_dev.store.Store` and use the primitive directly; there is no
  replacement wrapper, by design.
- `crossref_local.configure(db_path)` — there is no database path to
  configure. `configure_http()` / `configure_remote()` are unchanged.
- `Config.get_db_path()`, `Config.set_db_path()`, `DEFAULT_DB_PATHS` and the
  module-level `get_db_path()`.
- The `CROSSREF_LOCAL_DB` and `SCITEX_SCHOLAR_CROSSREF_DB` environment
  variables. The store connection is resolved by
  `scitex_dev.store.host_store()`, which reads `SCITEX_STORE_DSN`.
- The multi-day bulk build pipeline under `scripts/database/`, and
  `scripts/create_test_db.py`. They produced an artifact that no longer
  exists.
- The `tables` and `indices` arrays from the `/api/stats/` response. They
  were read out of the old engine's system catalog and have no equivalent.

### Added
- `_core/store.py` — the `Schema` declarations for the five collections
  (`crossref_works`, `crossref_citations`, `crossref_journals`,
  `crossref_corpus_stats`, `crossref_sync_state`) and the openers that hand
  out a bare `Store`.
- `_core/ingest.py` — the differential updater, previously a script loaded
  by file path that reached into `vendor/` for a row model. It is now an
  ordinary module behind `crossref-local update-db`.
- `Config.describe_store()` and `store_available()`.
- `docs/adr/` and ADR-0001.

### Changed
- **`scitex-dev` is now a hard dependency pinned at `>=0.57.0`** (was
  `>=0.11.5`), the release with one storage engine and the ephemeral-store
  test helpers.
- Searchable text (`title` / `abstract` / `authors`) is written onto the
  work record in the same upsert as the record itself, so a work can no
  longer be present but unsearchable because a second index write was
  skipped.
- `info()` reports a credential-free `store` description in place of
  `db_path`. Its `counts_source` is now `"exact"` or `"unavailable"`: the
  cheap row-count estimate was a property of the old file format and has no
  replacement, so an unmeasured count is reported as unknown rather than
  guessed.
- `refresh_stats()` no longer takes a path argument; `update()` no longer
  takes `db_path`; the citation and search functions take `store=` where
  they took `db=`.
- Full-text search is evaluated in Python over the works collection. The
  store primitive has no text-search, filtered-read or aggregate surface,
  so this is a full scan and a real regression at corpus scale. ADR-0001
  records it as a gap in the primitive rather than a local problem.

## [0.8.1] - 2026-07-22

Release note: the v0.8.0 tag exists but was NEVER published to PyPI —
its release workflow failed at the audit test gate (run 29887502634;
PyPI still had 0.7.6). 0.8.1 carries the audit fixes and ships the
0.8.0 feature set.

### Changed
- **CLI renames (audit-canonical verbs), old spellings kept as hidden
  warn-phase deprecated aliases (removed in 0.10):**
  - `refresh-stats` → `sync-stats` (§1f: 'refresh' is a non-canonical
    synonym of sync; the Python API `refresh_stats()` is unchanged)
  - `update` → `update-db` (§1: bare transitive verb at top level)
  - top-level `skills` → `dev skills` (§13: self-maintenance nests
    under `dev`)
- `update-db` no longer prompts interactively: a real run without
  `--yes/-y` refuses with exit 2 (§2 non-interactive CLI contract;
  `click.confirm` removed)
- `sync-stats` gained the §2 mutating-verb contract: `--yes/-y` required
  for a real run (refuses with exit 2), `--dry-run` shows the current
  cache/estimate state without writing
- `sync-stats` / `update-db` help is spec-built via CliHelp (§4b)
- CI runners (PS-169, operator mandate 2026-07-14): deleted the
  `newb-docs-quality-on-ubuntu-latest` workflow (fleet directive);
  Sphinx docs build now runs on the self-hosted pool via `CI_RUNS_ON`

### Fixed
- Audit conformance test (`tests/develop/test_audit.py`) passes again:
  §1f exemptions for the pre-existing `check-citations` / `show-status`
  verbs (`.scitex/dev/cli-audit-dict.yaml` `verb_exceptions:` with
  inline whys), §4b grandfathered for the 12 legacy free-form help
  screens, both tracked in card crossref-local-develop-ci-red-audit;
  the audit now grades the checkout under test via an explicit `path`
- STX-TQ005 fixture hygiene: resource-acquiring fixtures in
  `test_stats.py` / `test_cli_update.py` now `yield` with teardown

## [0.8.0] - 2026-07-22

### Added
- **`db_stats` exact-count cache** (`_core/stats.py`) — small table
  `db_stats(table_name TEXT PRIMARY KEY, row_count INTEGER, computed_at TEXT)`
  holding exact `COUNT(*)` results for `works` / `works_fts` / `citations`
- `refresh_stats()` public API + `crossref-local refresh-stats` CLI command —
  compute exact counts and write the cache (the only write path; also wired
  into `crossref-local update` after a successful sync)
- `counts_source` (`"exact"` / `"estimated"` / `"unavailable"`) and
  `counts_computed_at` fields in `info()` and the HTTP `/info` response —
  estimates are never silently presented as exact

### Changed
- **`info()` no longer full-scans large tables** (DB mode, async `aio.info()`,
  and the server `/info` endpoint). Production measurements (2026-07-22):
  `COUNT(*)` on works=167,008,748 rows took 0.42s, works_fts 12.70s (FTS5
  scans everything), citations=1,788,599,072 rows 4.35s — ~17.5s per call.
  Counts now come from the `db_stats` cache (exact) or `MAX(rowid)` estimates
  (~0.02s); `info()` needs no write access, so read-only deployments work

## [0.4.0] - 2026-01-24

### Added
- **Collections API** - HTTP endpoints for paper collections (`/collections/*`)
  - CRUD operations: list, create, query, delete
  - Download as JSON, CSV, BibTeX, or DOIs
  - Statistics endpoint for collection analytics
- **Citation HTTP endpoints** - RESTful citation access
  - `GET /citations/{doi}/citing` - Papers citing this DOI
  - `GET /citations/{doi}/cited` - Papers cited by this DOI
  - `GET /citations/{doi}/count` - Citation count
  - `GET /citations/{doi}/network` - Citation network graph
- **Multi-tenant support** - X-User-ID header for collection scoping
- **Security hardening**
  - Path traversal protection via name sanitization
  - Input validation with field whitelist (14 allowed fields)
  - Size limits: MAX_LIMIT=10000, MAX_DOIS=1000
- Shell completion command (`crossref-local completion bash/zsh/fish/install/status`)
- Paper cache module for efficient collection management
- MCP subcommand group (`crossref-local mcp {start,doctor,installation,list-tools}`)
- `--help-recursive` option for complete CLI help
- Remote deployment docs with systemd and Docker examples
- Automated MCP server installation via Makefile
- RemoteClient collection methods mixin

### Changed
- Default port changed from 8333 to 31291 (SCITEX convention)
- Server refactored into modular package (`server/`)
- Reorganized CLI commands for better clarity
- Improved MCP tools alignment with CLI commands
- SCITEX environment variables supported with fallback chain
- Examples renamed to follow numbered convention (04_mcp_demo)
- Updated .env.example with all environment variables

### Fixed
- Remote client `get_many` batch response includes citation_count
- CI workflow now includes pytest-cov for coverage reporting
- Circular import between cache.py and cache_export.py

## [0.3.1] - 2026-01-14

### Added
- FastAPI HTTP server with RESTful endpoints (`/works`, `/works/{doi}`, `/works/batch`)
- MCP server for Claude Desktop integration (`crossref-local serve`)
- Remote client for accessing API over SSH tunnel
- Comprehensive test suite (114 tests covering all modules)
- Shell scripts with proper usage/help options

### Changed
- Renamed API endpoints to RESTful conventions (`/search` → `/works`)
- Cleaned up Python API exposure - internal modules no longer in `__all__`
- Improved module docstrings with full API documentation

### Fixed
- Database threading issue under multi-threaded FastAPI access — the
  connection was shared across worker threads by a driver that could not
  be. (The engine named in the original wording is recorded in
  `docs/adr/0001-corpus-moves-to-the-shared-store.md`, which is the one
  place a retired engine may still be named.)
- Batch endpoint path in remote client
- FastMCP API compatibility (`description` → `instructions`)

## [0.3.0] - 2026-01-11

### Added
- CLI `-a/--with-abstracts` flag to display abstracts in search results
- Composed README figure combining IF validation and citation network
- Citation network visualization using figrecipe graph()
- GitHub Actions CI workflow
- Binder support for interactive notebooks
- Async API (`crossref_local.aio`)

### Changed
- Simplified README with collapsible sections
- Improved figure sizing for consistency (40x28mm)
- White backgrounds for all figures

### Fixed
- Figure margins for consistent sizing
- `fig.savefig` for proper white backgrounds

## [0.2.0] - 2026-01-10

### Added
- Impact factor validation examples with JCR comparison
- OpenAlex-based journal lookup for fast ISSN resolution
- SciTeX branding and AGPL-3.0 license

### Changed
- Moved validation figure to top of README

## [0.1.0] - 2026-01-09

### Added
- Initial release
- Core Python API: `search()`, `get()`, `count()`, `exists()`, `info()`
- Full-text search via FTS5 across 167M+ records
- Impact factor calculation from citation data
- Citation network analysis (`get_citing()`, `get_cited()`, `CitationNetwork`)
- CLI with commands: search, get, count, info, impact-factor
- Command aliases (s, g, c, i, if)

<!-- EOF -->
