<!-- ---
!-- Timestamp: 2026-01-16 19:15:51
!-- Author: ywatanabe
!-- File: /home/ywatanabe/proj/crossref-local/README.md
!-- --- -->

# CrossRef Local (<code>crossref-local</code>)

<p align="center">
  <a href="https://scitex.ai">
    <img src="docs/scitex-logo-blue-cropped.png" alt="SciTeX" width="400">
  </a>
</p>

<p align="center"><b>Local CrossRef database with 167M+ scholarly works, full-text search, and impact factor calculation</b></p>

## Demo

<p align="center">
  <img src="examples/readme_figure.png" alt="CrossRef Local Demo" width="800"/>
</p>

```bash
# Search 167M papers locally — no API rate limits, no API keys
crossref-local search "epilepsy seizure prediction"

# Resolve a DOI to full record (title, abstract, citations, journal IF)
crossref-local search-by-doi 10.1038/nature11247

# Drive from MCP / Claude Code
crossref-local mcp serve
```

The image is a live capture against the local store; the `<details>`
block below has a 6m55s MCP-driven demo video.

## Architecture

```
┌──────────────────────────┐    ┌──────────────────────────┐
│ CrossRef REST API        │    │ OpenAlex journal metadata│
│ (paged incrementally)    │    │ (impact factors)         │
└──────────────┬───────────┘    └──────────────┬───────────┘
               │ crossref-local update-db      │
               ▼                               ▼
   ┌───────────────────────────────────────────────────┐
   │ this host's shared store (scitex_dev.store)       │
   │   works · citations · journals · corpus_stats     │
   └───────────────────────┬───────────────────────────┘
                           │
                           ▼
   ┌──────────────────────────────────┐
   │ crossref-local — Python / CLI / MCP │
   │   search · search-by-doi · cache    │
   │   stats · check-citations · relay   │
   └──────────────────────────────────┘
```

The corpus lives in the fleet's shared store — one PostgreSQL-backed store
per host, resolved by `scitex_dev.store.host_store()`. `crossref-local` is a
thin facade over its `works`, `citations` and `journals` collections: no
database file to place, no path to configure, no download step.
`crossref-local update-db` is the only producer of state.

[![PyPI version](https://badge.fury.io/py/crossref-local.svg)](https://badge.fury.io/py/crossref-local)
[![Documentation](https://readthedocs.org/projects/crossref-local/badge/?version=latest)](https://crossref-local.readthedocs.io/en/latest/)
[![Tests](https://github.com/ywatanabe1989/crossref-local/actions/workflows/test.yml/badge.svg)](https://github.com/ywatanabe1989/crossref-local/actions/workflows/test.yml)
[![Coverage](https://codecov.io/gh/ywatanabe1989/crossref-local/branch/main/graph/badge.svg)](https://codecov.io/gh/ywatanabe1989/crossref-local)
[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-AGPL--3.0-blue.svg)](LICENSE)

<details>
<summary><strong>MCP Demo Video</strong></summary>

<p align="center">
  <a href="https://scitex.ai/media/videos/crossref-local-v0.3.1-demo.mp4">
    <img src="examples/04_mcp_demo_out/crossref-local-v0.3.1-demo-thumbnail_6m55s.png" alt="Demo Video Thumbnail" width="600"/>
  </a>
</p>

Live demonstration of MCP server integration with Claude Code for `epilepsy seizure prediction` literature review:
- Full-text search on title, abstracts, and keywords across 167M papers

📄 [Full demo documentation](examples/demo_mcp.org) | 📊 [Generated diagrams](examples/04_mcp_demo_out/)

</details>

<details>
<summary><strong>Why CrossRef Local?</strong></summary>

**Built for the LLM era** - features that matter for AI research assistants:

| Feature | Benefit |
|---------|---------|
| 📝 **Abstracts** | Full text for semantic understanding |
| 📊 **Impact Factor** | Filter by journal quality |
| 🔗 **Citations** | Prioritize influential papers |
| 🔓 **No gatekeeping** | Local reads — no API key, no quota, no throttling |

Perfect for: RAG systems, research assistants, literature review automation.

</details>

<details>
<summary><strong>Installation</strong></summary>

```bash
pip install crossref-local
```

From source:
```bash
git clone https://github.com/ywatanabe1989/crossref-local
cd crossref-local && make install
```

Store setup — nothing to download, nothing to build:
```bash
# 1. The corpus lives in this host's shared store. scitex-dev resolves it
#    from SCITEX_STORE_DSN; leave it unset to use this host's own store.
export SCITEX_STORE_DSN=...   # optional override

# 2. Populate / refresh incrementally from the CrossRef REST API
crossref-local update-db --yes

# 3. Refresh the exact-count cache that `status` and `info()` read
crossref-local sync-stats
```

`update-db` pages the CrossRef REST API from the last recorded sync date and
upserts what it finds, so it is both the initial fill and the ongoing
refresh. Run it under cron with `--yes --quiet`.

</details>

<details>
<summary><strong>Python API</strong></summary>

```python
from crossref_local import search, get, count

# Full-text search
results = search("hippocampal sharp wave ripples")
for work in results:
    print(f"{work.title} ({work.year})")

# Get by DOI
work = get("10.1126/science.aax0758")
print(work.citation())

# Count matches
n = count("machine learning")  # 477,922 matches
```

Async API:
```python
from crossref_local import aio

async def main():
    counts = await aio.count_many(["CRISPR", "neural network", "climate"])
    results = await aio.search("machine learning")
```

</details>

<details>
<summary><strong>CLI</strong></summary>

```bash
crossref-local search "CRISPR genome editing" -n 5
crossref-local search-by-doi 10.1038/nature12373
crossref-local status  # Configuration and database stats
```

With abstracts (`-a` flag):
```
$ crossref-local search "RS-1 enhances CRISPR" -n 1 -a

Found 4 matches

1. RS-1 enhances CRISPR/Cas9- and TALEN-mediated knock-in efficiency (2016)
   DOI: 10.1038/ncomms10548
   Journal: Nature Communications
   Abstract: Zinc-finger nuclease, transcription activator-like effector nuclease
   and CRISPR/Cas9 are becoming major tools for genome editing...
```

</details>

<details>
<summary><strong>HTTP API</strong></summary>

Start the FastAPI server:
```bash
crossref-local relay --host 0.0.0.0 --port 31291
```

Endpoints:
```bash
# Search works
curl "http://localhost:31291/works?q=CRISPR&limit=10"

# Get by DOI
curl "http://localhost:31291/works/10.1038/nature12373"

# Batch DOI lookup
curl -X POST "http://localhost:31291/works/batch" \
  -H "Content-Type: application/json" \
  -d '{"dois": ["10.1038/nature12373", "10.1126/science.aax0758"]}'

# Citation endpoints
curl "http://localhost:31291/citations/10.1038/nature12373/citing"
curl "http://localhost:31291/citations/10.1038/nature12373/cited"
curl "http://localhost:31291/citations/10.1038/nature12373/count"

# Collection endpoints
curl "http://localhost:31291/collections"
curl -X POST "http://localhost:31291/collections" \
  -H "Content-Type: application/json" \
  -d '{"name": "my_papers", "query": "CRISPR", "limit": 100}'
curl "http://localhost:31291/collections/my_papers/download?format=bibtex"

# Database info
curl "http://localhost:31291/info"
```

HTTP mode (connect to running server):
```bash
# On local machine (if server is remote)
ssh -L 31291:127.0.0.1:31291 your-server

# Python client
from crossref_local import configure_http
configure_http("http://localhost:31291")

# Or via CLI
crossref-local --http search "CRISPR"
```

</details>

<details>
<summary><strong>MCP Server</strong></summary>

Run as MCP (Model Context Protocol) server:
```bash
crossref-local mcp start
```

Local MCP client configuration:
```json
{
  "mcpServers": {
    "crossref-local": {
      "command": "crossref-local",
      "args": ["mcp", "start"],
      "env": {
        "SCITEX_STORE_DSN": "postgresql://…"
      }
    }
  }
}
```

Remote MCP via HTTP (recommended):
```bash
# On server: start persistent MCP server
crossref-local mcp start -t http --host 0.0.0.0 --port 8082
```
```json
{
  "mcpServers": {
    "crossref-remote": {
      "url": "http://your-server:8082/mcp"
    }
  }
}
```

`SCITEX_STORE_DSN` is optional — omit it and `scitex-dev` resolves this
host's own store.

Diagnose setup:
```bash
crossref-local mcp doctor        # Check dependencies and store
crossref-local mcp list-tools    # Show available MCP tools
crossref-local mcp installation  # Show client config examples
```

See [docs/remote-deployment.md](docs/remote-deployment.md) for systemd and Docker setup.

Available tools:
- `search` - Full-text search across 167M+ papers
- `search_by_doi` - Get paper by DOI
- `enrich_dois` - Add citation counts and references to DOIs
- `status` - Database statistics
- `cache_*` - Paper collection management

</details>

<details>
<summary><strong>Impact Factor</strong></summary>

```python
from crossref_local.impact_factor import ImpactFactorCalculator

with ImpactFactorCalculator() as calc:
    result = calc.calculate_impact_factor("Nature", target_year=2023)
    print(f"IF: {result['impact_factor']:.3f}")  # 54.067
```

| Journal | IF 2023 |
|---------|---------|
| Nature | 54.07 |
| Science | 46.17 |
| Cell | 54.01 |
| PLOS ONE | 3.37 |

</details>

<details>
<summary><strong>Citation Network</strong></summary>

```python
from crossref_local import get_citing, get_cited, CitationNetwork

citing = get_citing("10.1038/nature12373")  # 1539 papers
cited = get_cited("10.1038/nature12373")

# Build visualization (like Connected Papers)
network = CitationNetwork("10.1038/nature12373", depth=2)
network.save_html("citation_network.html")  # requires: pip install crossref-local[viz]
```

</details>

<details>
<summary><strong>Performance</strong></summary>

DOI lookups — `get()`, `get_many()`, `exists()` — are keyed reads on the
store and stay cheap at any corpus size.

**Full-text search does not.** `search()` and `count()` match in Python over
every record in the works collection, because the store primitive offers no
text search, no filtered read and no aggregate. That is one full scan of the
collection per query: correct at any size, acceptable only at small ones,
and not viable against the full ~167M-work corpus. The fix is a query
surface on the store primitive, which does not exist yet; until it does,
this is a real regression against the previous file-backed engine and is
stated here rather than hidden. See `crossref_local._core.fts` and the ADR
under `docs/adr/`.

Counts are never measured on the read path. `info()` reports
`counts_source: "exact"` from the cache that `crossref-local sync-stats`
writes, or `"unavailable"` when that cache is absent — it does not fall back
to counting, because counting means reading every record.

</details>

<details>
<summary><strong>Related Projects</strong></summary>

**[openalex-local](https://github.com/ywatanabe1989/openalex-local)** - Sister project with OpenAlex data:

| Feature | crossref-local | openalex-local |
|---------|----------------|----------------|
| Works | 167M | 284M |
| Abstracts | ~21% | ~45-60% |
| Update frequency | Real-time | Monthly |
| DOI authority | ✓ (source) | Uses CrossRef |
| Citations | Raw references | Linked works |
| Concepts/Topics | ❌ | ✓ |
| Author IDs | ❌ | ✓ |
| Best for | DOI lookup, raw refs | Semantic search |

**When to use CrossRef**: Real-time DOI updates, raw reference parsing, authoritative metadata.
**When to use OpenAlex**: Semantic search, citation analysis, topic discovery.

</details>

## Installation

Requirements: Python 3.10+, `scitex-dev>=0.57.0`, and access to this host's
shared store.

```bash
pip install crossref-local              # core
pip install crossref-local[mcp]         # + MCP server
```

From source:
```bash
git clone https://github.com/ywatanabe1989/crossref-local
cd crossref-local && make install
```

## 4 Interfaces

<details open>
<summary><strong>Python API</strong></summary>

```python
from crossref_local import search, get, count

# Full-text search
results = search("hippocampal sharp wave ripples")
for work in results:
    print(f"{work.title} ({work.year})")

# Get by DOI
work = get("10.1126/science.aax0758")
print(work.citation())

# Count matches
n = count("machine learning")  # 477,922 matches
```

</details>

<details>
<summary><strong>CLI</strong></summary>

```bash
crossref-local search "CRISPR genome editing" -n 5
crossref-local search-by-doi 10.1038/nature12373
crossref-local status  # Configuration and database stats
```

</details>

<details>
<summary><strong>HTTP API</strong></summary>

See the [HTTP API section](#http-api) above for all endpoints.

</details>

<details>
<summary><strong>MCP Server</strong></summary>

See the [MCP Server section](#mcp-server) above for configuration.

</details>

## Part of SciTeX

`crossref-local` is part of [**SciTeX**](https://scitex.ai).

>Four Freedoms for Research
>
>0. The freedom to **run** your research anywhere — your machine, your terms.
>1. The freedom to **study** how every step works — from raw data to final manuscript.
>2. The freedom to **redistribute** your workflows, not just your papers.
>3. The freedom to **modify** any module and share improvements with the community.
>
>AGPL-3.0 — because we believe research infrastructure deserves the same freedoms as the software it runs on.

---

<p align="center">
  <a href="https://scitex.ai" target="_blank"><img src="docs/scitex-icon-navy-inverted.png" alt="SciTeX" width="40"/></a>
</p>