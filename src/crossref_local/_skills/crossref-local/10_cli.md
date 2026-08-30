---
description: |
  [TOPIC] Cli
  [DETAILS] Entry point: `crossref-local` (installs from `crossref_local.cli:main`)
tags: [crossref-local-cli, crossref-local]
package: crossref-local
skill: cli
---


# Command-Line Interface

Entry point: `crossref-local` (installs from `crossref_local.cli:main`)

## Global Options

```
crossref-local [--http] [--api-url URL] [--help-recursive] COMMAND
```

| Option | Description |
|--------|-------------|
| `--http` | Force HTTP mode (connect to relay server) |
| `--api-url URL` | API URL; also via `CROSSREF_LOCAL_API_URL` |
| `--help-recursive` | Print help for all subcommands |
| `--version` | Show version |

## Commands

### `search`

```
crossref-local search QUERY [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `-n N`, `--number N` | Number of results (default: 10) |
| `-o N`, `--offset N` | Skip first N results |
| `-a`, `--abstracts` | Show abstracts |
| `-A`, `--authors` | Show author list |
| `-if`, `--impact-factor` | Show OpenAlex impact factor |
| `--json` | Output as JSON |
| `--save FILE` | Save results to file |
| `--format {text,json,bibtex}` | Format for `--save` (default: json) |

```bash
crossref-local search "hippocampal sharp wave ripples"
crossref-local search "CRISPR" -n 20 -a -A --json
crossref-local search "machine learning" --save papers.bib --format bibtex
crossref-local search "epilepsy" -n 100 --save results.json
```

### `search-by-doi`

```
crossref-local search-by-doi DOI [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--json` | Output as JSON |
| `--citation` | Output formatted APA citation |
| `--save FILE` | Save to file |
| `--format {text,json,bibtex}` | Format for `--save` (default: json) |

```bash
crossref-local search-by-doi 10.1038/nature12373
crossref-local search-by-doi 10.1038/nature12373 --citation
crossref-local search-by-doi 10.1038/nature12373 --json
crossref-local search-by-doi 10.1038/nature12373 --save paper.bib --format bibtex
```

### `check`

```
crossref-local check [FILE] [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `FILE` | BibTeX file (.bib) or DOI list file |
| `-d DOI` | Check specific DOI (repeatable) |
| `-f {bibtex,doi-list,auto}` | Input format (default: auto-detect) |
| `--no-validate` | Skip metadata validation |
| `--no-suggest` | Skip enrichment suggestions |
| `--json` | Output as JSON |
| `--save FILE` | Save results to file |
| `--save-format {json,text}` | Format for `--save` |

```bash
crossref-local check bibliography.bib
crossref-local check dois.txt
crossref-local check -d 10.1038/nature12373 -d 10.1126/science.aax0758
crossref-local check bibliography.bib --json
crossref-local check bibliography.bib --save report.json
# From stdin
echo "10.1038/nature12373" | crossref-local check
```

### `status`

```
crossref-local status [--json]
```

Alias for `show-status`. Shows environment variables, the resolved store,
API health, and the cached corpus counts.

### `update-db`

Incrementally fill and refresh the corpus from the CrossRef REST API. This
replaces the retired bulk-build pipeline: there is no dump to download and
nothing to build, so this is both the initial population and the ongoing
update.

```
crossref-local update-db [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--since YYYY-MM-DD` | Override start date (default: last recorded sync) |
| `--dry-run` | Preview only — no API calls that write, no store changes |
| `-y`, `--yes` | **Required** for a real run (non-interactive contract) |
| `--quiet` | Minimal stdout, for cron |

```bash
crossref-local update-db --yes                      # since last sync
crossref-local update-db --yes --since 2026-03-01   # explicit start date
crossref-local update-db --dry-run                  # preview, no writes
crossref-local update-db --yes --quiet              # cron / unattended
```

Exit codes: `0` success, `1` update failed, `2` refused (`--yes` missing on
a mutating run). `update` is a deprecated alias for this command.

Point `CROSSREF_LOCAL_UPDATE_FEED` at a local JSON feed file to drive the
same code path with no network (CI, air-gapped hosts).

### `sync-stats`

Count every collection exactly and write the count cache that `status` and
`info()` read. Slow by design — it reads each collection in full — so run it
from the ingest pipeline or on a schedule, never in a hot path.

```bash
crossref-local sync-stats
```

Without it, `info()` reports `counts_source: "unavailable"` rather than a
number nobody measured. `refresh-stats` is a deprecated alias.

### `relay`

Run an HTTP relay server exposing this host's shared store over REST.

```
crossref-local relay [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--host HOST` | Bind host (default: 0.0.0.0, env: `CROSSREF_LOCAL_HOST`) |
| `--port PORT` | Port (default: 31291, env: `CROSSREF_LOCAL_PORT`) |
| `--force` | Kill existing process using the port |
| `--dry-run` | Show what would be started |

```bash
crossref-local relay
crossref-local relay --port 8080
crossref-local relay --force
```

Requires: `pip install fastapi uvicorn`

### `mcp`

MCP server subcommands. See [11_mcp.md](11_mcp.md).

```bash
crossref-local mcp start              # stdio (Claude Desktop)
crossref-local mcp start -t http      # HTTP transport
crossref-local mcp doctor             # diagnose dependencies + store
crossref-local mcp installation       # show client config
crossref-local mcp list-tools         # list MCP tools
crossref-local mcp list-tools -vvv    # with full docs
```

### `list-python-apis`

```
crossref-local list-python-apis [-v|-vv|-vvv] [-d DEPTH] [--json]
```

Lists Python API signatures (delegates to `scitex introspect api`).
