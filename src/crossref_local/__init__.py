"""
crossref_local - Local CrossRef database with full-text search.

A Python package for querying a local mirror of the CrossRef database
with 167M+ scholarly works, full-text search, and impact factor calculation.

Quick Start
-----------

Sync usage:
    >>> from crossref_local import search, get
    >>> results = search("hippocampal sharp wave ripples")
    >>> work = get("10.1126/science.aax0758")

Async usage:
    >>> from crossref_local import aio
    >>> results = await aio.search("machine learning")
    >>> counts = await aio.count_many(["CRISPR", "neural network"])

Configuration
-------------

DB mode (direct access to this host's shared store):
    Nothing to configure. The store is resolved by
    ``scitex_dev.store.host_store()``, which honours SCITEX_STORE_DSN.

HTTP mode (API access via HTTP):
    >>> from crossref_local import configure_http
    >>> configure_http("http://localhost:8333")
    Or set CROSSREF_LOCAL_API_URL environment variable.

    Typical setup with SSH tunnel:
    $ ssh -L 8333:127.0.0.1:8333 your-server  # In terminal
    >>> configure_http()  # Uses default localhost:8333

Public API
----------

Functions:
    search(query, limit, offset) -> SearchResult
    count(query) -> int
    get(doi) -> Work | None
    get_many(dois) -> list[Work]
    exists(doi) -> bool
    enrich(results) -> SearchResult
    enrich_dois(dois) -> list[Work]
    configure_remote(api_url) -> None
    get_mode() -> str
    info() -> dict

Citation functions:
    get_citing(doi) -> list[str]
    get_cited(doi) -> list[str]
    get_citation_count(doi) -> int

Classes:
    Work - Scholarly work with title, authors, DOI, etc.
    SearchResult - Container for search results
    CitationNetwork - Citation graph builder and visualizer

Modules:
    aio - Async versions of all API functions
"""

from __future__ import annotations

# ============================================================================
# .env-respect: walk up from CWD to $HOME, loading every .env we find.
# Runs as the very first thing on import so downstream config readers
# (env vars consumed in _core.config etc.) see project-local overrides.
# ============================================================================
try:
    from pathlib import Path as _Path

    # scitex-config exposes both ``PriorityConfig`` (the class) and
    # ``load_dotenv`` (the parent-walking helper that landed on develop
    # at eb9507e1 with ``walk_up`` + ``stop_at`` kwargs). Use the helper
    # as a classmethod when available, fall back to the module-level
    # function otherwise — same call signature either way.
    from scitex_config import PriorityConfig as _PC

    _loader = getattr(_PC, "load_dotenv", None)
    if _loader is None:
        from scitex_config import load_dotenv as _loader  # type: ignore[no-redef]
    _loader(walk_up=True, stop_at=str(_Path.home()))
    del _PC, _Path, _loader
except Exception:
    pass

# ============================================================================
# Runtime-state migration: move legacy ~/.scitex/crossref-local/<sub>/ entries
# into ~/.scitex/crossref-local/runtime/<sub>/ on first import. One-shot,
# best-effort — never blocks import.
# ============================================================================
try:
    from crossref_local._core.paths import _migrate_legacy_state as _mls

    _mls()
    del _mls
except Exception:
    pass

try:
    from importlib.metadata import version as _v, PackageNotFoundError

    try:
        __version__ = _v("crossref-local")
    except PackageNotFoundError:
        __version__ = "0.0.0+local"
    del _v, PackageNotFoundError
except ImportError:  # pragma: no cover — only on ancient Pythons
    __version__ = "0.0.0+local"
# Core API (from _core package)
from ._core import (
    # Functions
    search,
    count,
    get,
    get_many,
    exists,
    enrich,
    enrich_dois,
    configure_http,
    configure_remote,
    get_mode,
    info,
    refresh_stats,
    # Models
    Work,
    SearchResult,
    # Citations
    get_citing,
    get_cited,
    get_citation_count,
    CitationNetwork,
    # Export
    save,
    SUPPORTED_FORMATS,
    # Update (incremental refresh)
    update,
)

# Checker
from ._core.checker import (
    check_citations,
    check_bibtex,
    check_doi_list,
    CheckResult,
    CitationEntry,
)

# Async API (public module)
from . import aio

# Cache module (public)
from . import cache

# Jobs module (public)
from . import jobs

# Apply @supports_return_as decorator to key API functions
try:
    from scitex_dev.decorators import supports_return_as as _supports_return_as

    search = _supports_return_as(search)
    count = _supports_return_as(count)
    get = _supports_return_as(get)
    get_many = _supports_return_as(get_many)
    enrich_dois = _supports_return_as(enrich_dois)
    info = _supports_return_as(info)
    get_citing = _supports_return_as(get_citing)
    get_cited = _supports_return_as(get_cited)
    get_citation_count = _supports_return_as(get_citation_count)
    check_citations = _supports_return_as(check_citations)
    check_bibtex = _supports_return_as(check_bibtex)
    check_doi_list = _supports_return_as(check_doi_list)
except ImportError:
    pass


# Public API - what users should import
__all__ = [
    # Version
    "__version__",
    # Core search/retrieval
    "search",
    "count",
    "get",
    "get_many",
    "exists",
    # Enrichment (add citations/references to search results)
    "enrich",
    "enrich_dois",
    # Configuration
    "configure_http",
    "configure_remote",  # Backward compatibility alias
    "get_mode",
    "info",
    "refresh_stats",
    # Data models
    "Work",
    "SearchResult",
    # Async API
    "aio",
    # Cache module
    "cache",
    # Jobs module
    "jobs",
    # Citation network
    "get_citing",
    "get_cited",
    "get_citation_count",
    "CitationNetwork",
    # Export/Save
    "save",
    "SUPPORTED_FORMATS",
    # Incremental database update
    "update",
    # Citation checking
    "check_citations",
    "check_bibtex",
    "check_doi_list",
    "CheckResult",
    "CitationEntry",
]


# ============================================================================
# Advanced / Internal APIs (not in __all__, but importable if needed)
# ============================================================================
# These are exposed for advanced users but not part of the stable public API.
# Use at your own risk - they may change without notice.
#
# from crossref_local._core.store import works_store, WORKS
# from crossref_local.config import Config
# from crossref_local.remote import RemoteClient
# from crossref_local.fts import search_dois
# ============================================================================
